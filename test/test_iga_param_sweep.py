# -*- coding: utf-8 -*-
import os
import sys
import unittest

import networkx as nx


current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from src.routing.iga.iga_fitness import GAMMA, LAMBDA, calculate_fitness


class TestIGAParamSweep(unittest.TestCase):
    def setUp(self):
        self.graph = nx.Graph()
        self.graph.add_edge(
            "S",
            "A",
            delay=10.0,
            loss=0.01,
            capacity=100.0,
            used_bw=70.0,
        )
        self.graph.add_edge(
            "A",
            "D",
            delay=12.0,
            loss=0.01,
            capacity=100.0,
            used_bw=70.0,
        )
        self.path = ["S", "A", "D"]
        self.constraints = {
            "service_type": "Video_Live",
            "bandwidth": 5.0,
            "delay_req": 300.0,
        }

    def test_explicit_defaults_match_global_defaults(self):
        default_fit = calculate_fitness(self.graph, self.path, self.constraints)
        explicit_fit = calculate_fitness(
            self.graph,
            self.path,
            dict(self.constraints, iga_gamma=GAMMA, iga_lambda=LAMBDA),
        )
        self.assertAlmostEqual(default_fit, explicit_fit, places=10)

    def test_higher_gamma_lambda_reduce_fitness_for_busy_path(self):
        base_fit = calculate_fitness(self.graph, self.path, self.constraints)
        tuned_fit = calculate_fitness(
            self.graph,
            self.path,
            dict(self.constraints, iga_gamma=4.0, iga_lambda=2.0),
        )
        self.assertLess(tuned_fit, base_fit)


if __name__ == "__main__":
    unittest.main()
