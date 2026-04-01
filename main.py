# -*- coding: utf-8 -*-
"""
File: main.py
Description: 异构星座路由仿真主入口
"""
import copy
import logging
import os
from datetime import datetime

import pandas as pd
from tqdm import tqdm

from config.settings import RESULTS_DIR
from src.routing.dijkstra import DijkstraStrategy
from src.routing.hierarchical_mapper import VirtualTopologyManager
from src.routing.iga.iga import IGAStrategy
from src.routing.iga.iga_fitness import evaluate_path
from src.routing.inter_algo import InterDomainAlgorithm
from src.simulation_utils import (
    decompose_and_execute_hierarchical as shared_decompose_and_execute_hierarchical,
    ensure_dir as shared_ensure_dir,
    get_sim_config,
    log_network_snapshot as shared_log_network_snapshot,
    manage_traffic as shared_manage_traffic,
)
from src.topology import TopologyManager
from src.traffic import TrafficGenerator
from src.utils import get_flow_logger, get_net_logger, get_session_dir

cfg = get_sim_config()
SIM_START = cfg['SIM_START']
SIM_DURATION = cfg['SIM_DURATION']
TIME_STEP = cfg['TIME_STEP']
REQUESTS_PER_STEP = cfg['REQUESTS_PER_STEP']

TRAFFIC_DATA_DIR = os.path.join("data", "traffic_cache_main")
SERVICE_TYPES = {
    'Voice_Critical': {'bandwidth': 1, 'delay_req': 180, 'loss_req': 0.001, 'priority': 0.8},
    'Remote_Sensing': {'bandwidth': 45, 'delay_req': 2000, 'loss_req': 0.01, 'priority': 0.3},
    'Best_Effort': {'bandwidth': 5, 'delay_req': 800, 'loss_req': 0.05, 'priority': 0.5},
}


def _apply_path_traffic(topo_mgr, G, path, bandwidth):
    for u, v in zip(path[:-1], path[1:]):
        topo_mgr.update_link_state(G, u, v, bandwidth)


def _build_remote_sensing_requests(traffic_gen, G, request_count, remote_sensing_bw):
    requests = []
    raw_requests = traffic_gen.generate_requests(G, num_requests=request_count)
    base_qos = {
        'bandwidth': remote_sensing_bw,
        'delay_req': SERVICE_TYPES['Remote_Sensing']['delay_req'],
        'loss_req': SERVICE_TYPES['Remote_Sensing']['loss_req'],
        'priority': SERVICE_TYPES['Remote_Sensing']['priority'],
        'service_type': 'Remote_Sensing',
    }
    for i, req in enumerate(raw_requests):
        req_copy = req.copy()
        req_copy.update(base_qos)
        req_copy['id'] = i
        requests.append(req_copy)
    return requests


def run_simulation(remote_sensing_bw=45, request_count=100, verbose=False):
    """
    Compatibility wrapper used by auto_tune.py.
    Runs one small comparison between flat Dijkstra and H-IGA on identical traffic.
    """
    flog = get_flow_logger()
    nlog = get_net_logger()
    if not verbose:
        flog.setLevel(logging.ERROR)
        nlog.setLevel(logging.ERROR)

    sim_time = SIM_START
    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    vtm = VirtualTopologyManager()

    algo_baseline = DijkstraStrategy(weight_key='static_delay')
    algo_iga = IGAStrategy()
    algo_inter = InterDomainAlgorithm()

    G_base = topo_mgr.get_graph_at_time(sim_time)
    requests = _build_remote_sensing_requests(traffic_gen, G_base, request_count, remote_sensing_bw)

    G_env_dijkstra = copy.deepcopy(G_base)
    G_env_higa = copy.deepcopy(G_base)
    G_vir_higa, phy_to_vir = vtm.build_virtual_graph(G_env_higa)

    dijkstra_losses = []
    dijkstra_delays = []
    higa_losses = []
    higa_delays = []
    higa_success = 0

    for req in requests:
        path_d, _ = algo_baseline.find_path(G_env_dijkstra, req['src'], req['dst'], req)
        if path_d:
            _apply_path_traffic(topo_mgr, G_env_dijkstra, path_d, req['bandwidth'])
            metrics_d = evaluate_path(G_env_dijkstra, path_d)
            dijkstra_losses.append(metrics_d['loss'])
            dijkstra_delays.append(metrics_d['delay'])

        src_v = phy_to_vir.get(req['src'], req['src'])
        dst_v = phy_to_vir.get(req['dst'], req['dst'])
        v_path, _ = algo_inter.find_path(G_vir_higa, src_v, dst_v, req)
        if not v_path:
            continue

        path_h, success_h, _, _ = shared_decompose_and_execute_hierarchical(
            None, G_env_higa, G_vir_higa, v_path, phy_to_vir, req['src'], req['dst'], req, algo_iga, topo_mgr
        )
        if success_h and path_h:
            _apply_path_traffic(topo_mgr, G_env_higa, path_h, req['bandwidth'])
            metrics_h = evaluate_path(G_env_higa, path_h)
            higa_losses.append(metrics_h['loss'])
            higa_delays.append(metrics_h['delay'])
            higa_success += 1

    def _safe_mean(values, default):
        if values:
            return float(sum(values) / len(values))
        return default

    return {
        'Dijk_Loss': _safe_mean(dijkstra_losses, 1.0),
        'HIGA_Succ': (higa_success / request_count) if request_count else 0.0,
        'HIGA_Loss': _safe_mean(higa_losses, 1.0),
        'Dijk_Delay': _safe_mean(dijkstra_delays, 0.0),
        'HIGA_Delay': _safe_mean(higa_delays, 0.0),
    }


def main():
    flog = get_flow_logger()
    nlog = get_net_logger()
    session_dir = get_session_dir()
    routing_info_dir = os.path.join(session_dir, 'routing_info')

    flog.info("========================================================")
    flog.info("[HeteroSat Sim] 平行对比仿真 (最终定稿版)")
    flog.info(f"   - 结果目录: {session_dir}")
    flog.info("========================================================")

    shared_ensure_dir(routing_info_dir)
    shared_ensure_dir(RESULTS_DIR)

    topo_mgr = TopologyManager()
    traffic_gen = TrafficGenerator(topo_mgr)
    vtm = VirtualTopologyManager()

    algo_baseline = DijkstraStrategy(weight_key='static_delay')
    algo_iga = IGAStrategy()
    algo_inter = InterDomainAlgorithm()
    all_results = []

    with open(os.path.join(routing_info_dir, "dijkstra_paths.txt"), 'w', encoding='utf-8') as f_dijk, \
         open(os.path.join(routing_info_dir, "h_iga_paths.txt"), 'w', encoding='utf-8') as f_higa:
        for sim_time in range(SIM_START, SIM_START + SIM_DURATION, TIME_STEP):
            flog.info(f"\n[Time {sim_time}s] 初始化环境...")

            G_base = topo_mgr.get_graph_at_time(sim_time)
            G_vir, phy_to_vir = vtm.build_virtual_graph(G_base)
            requests = shared_manage_traffic(traffic_gen, G_base, sim_time, REQUESTS_PER_STEP, TRAFFIC_DATA_DIR)

            G_env_dijkstra = copy.deepcopy(G_base)
            G_env_higa = copy.deepcopy(G_base)

            flog.info("   [Group A] Running Dijkstra...")
            for req in requests:
                t0 = datetime.now()
                path, _ = algo_baseline.find_path(G_env_dijkstra, req['src'], req['dst'], req)
                dt = (datetime.now() - t0).total_seconds() * 1000

                res = {
                    'Time': sim_time,
                    'ID': req['id'],
                    'Type': req['service_type'],
                    'Algo': 'Dijkstra',
                    'Success': bool(path),
                    'TimeCost': dt,
                }

                if path:
                    f_dijk.write(f"T={sim_time}, ID={req['id']}\n  {path}\n")
                    _apply_path_traffic(topo_mgr, G_env_dijkstra, path, req['bandwidth'])
                    metrics = evaluate_path(G_env_dijkstra, path)
                    res.update({'Delay': metrics['delay'], 'Loss': metrics['loss'], 'Hops': len(path)})
                else:
                    res.update({'Delay': None, 'Loss': None, 'Hops': None})
                all_results.append(res)

            flog.info("   [Group B] Running H-IGA...")
            for req in tqdm(requests, desc="H-IGA"):
                t0 = datetime.now()
                src_v = phy_to_vir.get(req['src'], req['src'])
                dst_v = phy_to_vir.get(req['dst'], req['dst'])
                v_path, _ = algo_inter.find_path(G_vir, src_v, dst_v, req)

                path, success, trace_log, fail_reason = None, False, [], "Unknown"
                if v_path:
                    path, success, trace_log, fail_reason = shared_decompose_and_execute_hierarchical(
                        flog, G_env_higa, G_vir, v_path, phy_to_vir, req['src'], req['dst'], req, algo_iga, topo_mgr
                    )
                else:
                    fail_reason = "No Virtual Path (Inter-domain fail)"
                    trace_log.append("Virtual Topology Routing Failed")

                dt = (datetime.now() - t0).total_seconds() * 1000
                res = {
                    'Time': sim_time,
                    'ID': req['id'],
                    'Type': req['service_type'],
                    'Algo': 'H-IGA',
                    'Success': success,
                    'TimeCost': dt,
                }

                f_higa.write(f"T={sim_time}, ID={req['id']} [{'SUCCESS' if success else 'FAILED'}]\n")
                if success and path:
                    f_higa.write("  Result: Success\n")
                    for line in trace_log:
                        f_higa.write(f"  {line}\n")
                    f_higa.write("\n")

                    _apply_path_traffic(topo_mgr, G_env_higa, path, req['bandwidth'])
                    metrics = evaluate_path(G_env_higa, path)
                    res.update({'Delay': metrics['delay'], 'Loss': metrics['loss'], 'Hops': len(path)})
                else:
                    f_higa.write("  Result: FAILED\n")
                    f_higa.write(f"  Reason: {fail_reason}\n")
                    f_higa.write("  Trace:\n")
                    for line in trace_log:
                        f_higa.write(f"    {line}\n")
                    f_higa.write("\n")
                    res.update({'Delay': None, 'Loss': None, 'Hops': None})

                all_results.append(res)

            shared_log_network_snapshot(nlog, G_env_dijkstra, sim_time, "Dijkstra_World")
            shared_log_network_snapshot(nlog, G_env_higa, sim_time, "H-IGA_World")

    if all_results:
        df = pd.DataFrame(all_results)
        csv_path = os.path.join(session_dir, "sim_metrics_parallel.csv")
        df.to_csv(csv_path, index=False)
        print("\n平行仿真结果摘要:")
        print(df[df['Success'] == True].groupby(['Algo', 'Type'])[['Delay', 'Loss']].mean())
        print(f"\n结果已保存: {session_dir}")


if __name__ == "__main__":
    main()
