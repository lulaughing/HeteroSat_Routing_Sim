# -*- coding: utf-8 -*-
"""
Run an isolated H-IGA intra-domain gamma/lambda parameter sweep.

This experiment intentionally keeps the inter-domain routing model fixed and
only varies the congestion penalty parameters used by the intra-domain H-IGA
fitness function.
"""
import copy
import os
import sys

import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(PROJECT_ROOT)

from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.iga.iga import IGAStrategy
from src.routing.iga.iga_fitness import evaluate_path
from src.routing.inter_algo import InterDomainAlgorithm
from src.simulation_utils import (
    decompose_and_execute_hierarchical,
    ensure_dir,
    get_sim_config,
    manage_traffic,
)
from src.topology import TopologyManager
from src.traffic import TrafficGenerator


RESULT_ROOT = os.path.join(PROJECT_ROOT, "data", "result_for_param_higa_gamma_lambda")
RAW_DIR = os.path.join(RESULT_ROOT, "raw")
PROC_DIR = os.path.join(RESULT_ROOT, "proc")
PLOTS_DIR = os.path.join(RESULT_ROOT, "plots")
DETAILS_PATH = os.path.join(RAW_DIR, "higa_gamma_lambda_details.csv")
SUMMARY_PATH = os.path.join(RAW_DIR, "higa_gamma_lambda_summary.csv")
TRAFFIC_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "traffic_cache_load_analysis")

DEFAULT_LOADS = [300, 400, 500, 600]
DEFAULT_GAMMAS = [0.5, 1.0, 2.0, 3.0]
DEFAULT_LAMBDAS = [0.5, 1.0, 1.5, 2.0]
LOSS_THRESHOLD = 0.05


def _parse_list(env_name, default_values, caster):
    raw_value = os.environ.get(env_name, "").strip()
    if not raw_value:
        return list(default_values)

    parsed = []
    for item in raw_value.split(","):
        item = item.strip()
        if not item:
            continue
        parsed.append(caster(item))
    return parsed or list(default_values)


def _reset_link_usage(graph):
    for _, _, data in graph.edges(data=True):
        data["used_bw"] = 0.0


def _build_requests(topo_mgr, traffic_gen, virtual_mgr, load):
    cfg = get_sim_config()
    sim_time = cfg["SIM_START"]
    graph_phy = topo_mgr.get_graph_at_time(sim_time)
    graph_vir, phy_to_vir = virtual_mgr.build_virtual_graph(graph_phy)
    requests = manage_traffic(
        traffic_gen,
        graph_phy,
        sim_time,
        load,
        TRAFFIC_CACHE_DIR,
    )
    return graph_phy, graph_vir, phy_to_vir, requests


def _run_single_combo(load, gamma_value, lambda_value, topo_mgr, traffic_gen, virtual_mgr):
    graph_phy_base, graph_vir_base, phy_to_vir, requests = _build_requests(
        topo_mgr, traffic_gen, virtual_mgr, load
    )

    graph_phy = copy.deepcopy(graph_phy_base)
    graph_vir = copy.deepcopy(graph_vir_base)
    _reset_link_usage(graph_phy)
    _reset_link_usage(graph_vir)

    algo_inter = InterDomainAlgorithm()
    algo_intra = IGAStrategy(pop_size=25, max_iter=25, p_guide=0.7)

    details = []
    progress_desc = f"Load={load} gamma={gamma_value} lambda={lambda_value}"
    for request in tqdm(requests, desc=progress_desc, leave=False):
        req = dict(request)
        req["iga_gamma"] = gamma_value
        req["iga_lambda"] = lambda_value

        src = req["src"]
        dst = req["dst"]
        bandwidth = req["bandwidth"]
        src_vir = phy_to_vir.get(src, src)
        dst_vir = phy_to_vir.get(dst, dst)

        vir_path, _ = algo_inter.find_path(graph_vir, src_vir, dst_vir, req)
        path = None
        found = False
        note = "Inter-Fail"

        if vir_path:
            path, found, _, note = decompose_and_execute_hierarchical(
                None,
                graph_phy,
                graph_vir,
                vir_path,
                phy_to_vir,
                src,
                dst,
                req,
                algo_intra,
                topo_mgr,
            )

        if found and path:
            for hop_u, hop_v in zip(path[:-1], path[1:]):
                topo_mgr.update_link_state(graph_phy, hop_u, hop_v, bandwidth)

        path_metrics = {"delay": 0.0, "loss": 1.0, "max_util": 0.0}
        real_success = False
        if found and path:
            path_metrics = evaluate_path(graph_phy, path)
            if path_metrics["loss"] <= LOSS_THRESHOLD:
                real_success = True
            else:
                note = f"HighLoss ({path_metrics['loss']:.1%})"

        real_goodput = 0.0
        if real_success:
            real_goodput = max(bandwidth * (1.0 - path_metrics["loss"]), 0.0)

        details.append(
            {
                "ID": req["id"],
                "Algo": "H-IGA",
                "Load": load,
                "Gamma": gamma_value,
                "Lambda": lambda_value,
                "Success": real_success,
                "Bandwidth": bandwidth,
                "Goodput": real_goodput,
                "Delay": path_metrics["delay"] if path else 0.0,
                "Loss": path_metrics["loss"],
                "Hops": len(path) if path else 0,
                "MaxUtil": path_metrics["max_util"] if path else 0.0,
                "Note": "" if real_success else note,
            }
        )

    return pd.DataFrame(details)


def _summarize_combo(df):
    success_df = df[df["Success"] == True]
    return {
        "Algo": "H-IGA",
        "Load": int(df["Load"].iloc[0]),
        "Gamma": float(df["Gamma"].iloc[0]),
        "Lambda": float(df["Lambda"].iloc[0]),
        "PDR": df["Success"].mean() * 100.0 if not df.empty else 0.0,
        "Throughput": success_df["Bandwidth"].sum() if not success_df.empty else 0.0,
        "AvgGoodput": df["Goodput"].sum() if not df.empty else 0.0,
        "AvgDelay": success_df["Delay"].mean() if not success_df.empty else 0.0,
        "AvgLoss": df["Loss"].mean() * 100.0 if not df.empty else 0.0,
    }


def main():
    loads = _parse_list("HETEROSAT_PARAM_LOADS", DEFAULT_LOADS, int)
    gammas = _parse_list("HETEROSAT_PARAM_GAMMAS", DEFAULT_GAMMAS, float)
    lambdas = _parse_list("HETEROSAT_PARAM_LAMBDAS", DEFAULT_LAMBDAS, float)

    for output_dir in (RESULT_ROOT, RAW_DIR, PROC_DIR, PLOTS_DIR, TRAFFIC_CACHE_DIR):
        ensure_dir(output_dir)

    print("[H-IGA Parameter Sweep] Intra-domain gamma/lambda analysis")
    print(f"Output root: {RESULT_ROOT}")
    print(f"Loads: {loads}")
    print(f"Gammas: {gammas}")
    print(f"Lambdas: {lambdas}")

    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    virtual_mgr = VirtualTopologyManager()

    all_details = []
    summary_rows = []
    total_runs = len(loads) * len(gammas) * len(lambdas)

    with tqdm(total=total_runs, desc="Total Progress") as progress:
        for load in loads:
            for gamma_value in gammas:
                for lambda_value in lambdas:
                    df = _run_single_combo(
                        load, gamma_value, lambda_value, topo_mgr, traffic_gen, virtual_mgr
                    )
                    all_details.append(df)
                    summary_rows.append(_summarize_combo(df))
                    progress.update(1)

    details_df = pd.concat(all_details, ignore_index=True) if all_details else pd.DataFrame()
    summary_df = pd.DataFrame(summary_rows)

    if not details_df.empty:
        details_df = details_df.sort_values(by=["Load", "Gamma", "Lambda", "ID"]).reset_index(drop=True)
    if not summary_df.empty:
        summary_df = summary_df.sort_values(by=["Load", "Gamma", "Lambda"]).reset_index(drop=True)

    details_df.to_csv(DETAILS_PATH, index=False)
    summary_df.to_csv(SUMMARY_PATH, index=False)

    print("")
    print(f"Saved details: {DETAILS_PATH}")
    print(f"Saved summary: {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
