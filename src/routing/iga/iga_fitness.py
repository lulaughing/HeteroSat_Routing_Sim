# -*- coding: utf-8 -*-
"""
File: src/routing/iga/iga_fitness.py
Description: Fitness calculation for H-IGA (dynamic QoS + congestion aware)
"""
import math


# Normalization constants.
D_MAX = 2000.0
L_MAX = 0.1
LAMBDA = 1.0
GAMMA = 2.0


def _resolve_congestion_param(constraints, key, default):
    value = constraints.get(key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def get_congestion_params(constraints=None):
    """
    Resolve intra-domain H-IGA congestion parameters from request constraints.

    Parameter sweep scripts inject `iga_gamma` and `iga_lambda` through
    request constraints so the inter-domain routing model can stay fixed.
    """
    constraints = constraints or {}
    gamma = _resolve_congestion_param(constraints, "iga_gamma", GAMMA)
    lambda_ = _resolve_congestion_param(constraints, "iga_lambda", LAMBDA)
    return gamma, lambda_


def get_qos_weights(service_type):
    if service_type in ["Video_Live", "Voice_VoIP", "Telemetry_Control"]:
        return 0.8, 0.2
    if service_type == "Remote_Sensing":
        return 0.2, 0.8
    return 0.5, 0.5


def evaluate_path(G, path):
    """
    Compute physical path metrics used by the routing pipeline.
    """
    total_delay = 0.0
    success_prob = 1.0
    min_bw = float("inf")
    max_util = 0.0

    for u, v in zip(path[:-1], path[1:]):
        if not G.has_edge(u, v):
            continue

        attr = G[u][v]
        total_delay += attr.get("delay", 10.0)

        link_loss = attr.get("loss", 0.001)
        link_loss = max(0.0, min(1.0, link_loss))
        success_prob *= (1.0 - link_loss)

        capacity = attr.get("capacity", 200.0)
        used_bw = attr.get("used_bw", 0.0)
        remaining_bw = capacity - used_bw
        if remaining_bw < min_bw:
            min_bw = remaining_bw

        util = used_bw / capacity if capacity > 0 else 1.0
        if util > max_util:
            max_util = util

    total_loss = 1.0 - success_prob

    return {
        "delay": total_delay,
        "loss": total_loss,
        "min_bw": min_bw,
        "max_util": max_util,
        "max_load": max_util,
        "hops": max(0, len(path) - 1),
    }


def calculate_fitness(G, path, constraints):
    """
    H-IGA fitness calculation.
    """
    constraints = constraints or {}
    if not path:
        return 1e-15

    metrics = evaluate_path(G, path)
    service_type = constraints.get("service_type", "Unknown")
    alpha, beta = get_qos_weights(service_type)
    gamma, lambda_ = get_congestion_params(constraints)

    base_qos = (alpha * (metrics["delay"] / D_MAX)) + (beta * (metrics["loss"] / L_MAX))
    safe_util = min(metrics["max_util"], 5.0)
    congestion_penalty = 1.0 + lambda_ * math.exp(gamma * safe_util)
    total_cost = base_qos * congestion_penalty
    base_fitness = 1.0 / (total_cost + 1e-5)

    req_bw = constraints.get("bandwidth", 0.0)
    bw_penalty_coef = 1.0
    if metrics["min_bw"] < req_bw:
        shortage = req_bw - metrics["min_bw"]
        bw_penalty_coef = 0.05 / (1.0 + shortage)

    req_delay = constraints.get("delay_req", float("inf"))
    delay_penalty_coef = 1.0
    if metrics["delay"] > req_delay:
        violation = (metrics["delay"] - req_delay) / (req_delay + 1e-5)
        delay_penalty_coef = 0.1 / (1.0 + violation * 10.0)

    return base_fitness * bw_penalty_coef * delay_penalty_coef
