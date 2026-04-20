import numpy as np
import networkx as nx
from scipy.spatial.distance import pdist
from scipy.stats import kurtosis, skew, pearsonr, kendalltau
from scipy.signal import find_peaks
from scipy.cluster.hierarchy import fcluster, linkage
from pydantic import BaseModel, Field

from swarm.agents.society import AgentSociety, TickResult


class EmergenceEvent(BaseModel):
    """A detected emergent phenomenon."""
    event_type: str
    tick: int
    confidence: float
    metrics: dict[str, float] = Field(default_factory=dict)
    description: str = ""


class TimeSeriesStore:
    """Accumulates metric history for windowed computations."""

    def __init__(self, max_history: int = 500):
        self._max = max_history
        self._series: dict[str, list[float]] = {}
        self._vectors: list[np.ndarray] = []

    def record_metric(self, name: str, value: float) -> None:
        if name not in self._series:
            self._series[name] = []
        self._series[name].append(value)
        if len(self._series[name]) > self._max:
            self._series[name] = self._series[name][-self._max:]

    def record_vectors(self, vectors: np.ndarray) -> None:
        """Store agent belief vectors for this tick."""
        self._vectors.append(vectors.copy())
        if len(self._vectors) > self._max:
            self._vectors = self._vectors[-self._max:]

    def get(self, name: str, window: int | None = None) -> list[float]:
        series = self._series.get(name, [])
        if window is None:
            return series
        return series[-window:]

    def get_vectors(self, window: int | None = None) -> list[np.ndarray]:
        if window is None:
            return self._vectors
        return self._vectors[-window:]

    @property
    def tick_count(self) -> int:
        return len(self._vectors)

    @property
    def all_metrics(self) -> dict[str, list[float]]:
        return self._series.copy()


class OpinionMetrics:
    """Category A: Opinion/belief dynamics metrics."""

    def consensus(self, vectors: np.ndarray) -> float:
        """1.0 = perfect consensus, 0.0 = maximum disagreement."""
        if len(vectors) < 2:
            return 1.0
        dists = pdist(vectors, metric="euclidean")
        max_possible = np.sqrt(vectors.shape[1])
        return 1.0 - (np.mean(dists) / max_possible)

    def diameter(self, vectors: np.ndarray) -> float:
        """Max pairwise distance (opinion spread)."""
        if len(vectors) < 2:
            return 0.0
        return float(np.max(pdist(vectors, metric="euclidean")))

    def polarization(self, vectors: np.ndarray) -> float:
        """Bimodality coefficient. >5/9 suggests bimodal distribution."""
        if len(vectors) < 4:
            return 0.0
        centered = vectors - vectors.mean(axis=0)
        _, _, Vt = np.linalg.svd(centered, full_matrices=False)
        projected = centered @ Vt[0]
        n = len(projected)
        s = skew(projected)
        k = kurtosis(projected, fisher=False)
        denom = k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))
        if denom <= 0:
            return 0.0
        return float((s ** 2 + 1) / denom)

    def fragmentation(self, vectors: np.ndarray, distance_threshold: float = 0.5) -> dict[str, float]:
        """Effective number of opinion clusters and fragmentation index."""
        if len(vectors) < 2:
            return {"enp": 1.0, "fragmentation": 0.0, "num_clusters": 1}
        dists = pdist(vectors, "euclidean")
        Z = linkage(dists, method="ward")
        labels = fcluster(Z, t=distance_threshold, criterion="distance")
        k = len(set(labels))
        sizes = np.array([np.sum(labels == c) for c in set(labels)])
        p = sizes / sizes.sum()
        enp = 1.0 / np.sum(p ** 2)
        frag = 1.0 - np.max(p)
        return {"enp": float(enp), "fragmentation": float(frag), "num_clusters": k}

    def extremization(self, vectors: np.ndarray) -> dict[str, float]:
        """How far agents are from the center of opinion space."""
        D = vectors.shape[1]
        center = 0.5 * np.ones(D)
        dists_from_center = np.linalg.norm(vectors - center, axis=1)
        max_dist = 0.5 * np.sqrt(D)
        extremism_index = float(np.mean(dists_from_center / max_dist))
        tail_fraction = float(np.mean(dists_from_center > 0.8 * max_dist))
        return {"extremism_index": extremism_index, "tail_fraction": tail_fraction}

    def convergence_rate(self, variance_history: list[float], window: int = 10) -> float:
        """Rate of variance decay. Positive = converging, negative = diverging."""
        if len(variance_history) < window:
            return 0.0
        recent = np.array(variance_history[-window:])
        recent_clipped = np.clip(recent, 1e-12, None)
        log_var = np.log(recent_clipped)
        t_axis = np.arange(window)
        b, _ = np.polyfit(t_axis, log_var, 1)
        return float(-b)

    def variance(self, vectors: np.ndarray) -> float:
        """Total opinion variance (mean squared distance from centroid)."""
        if len(vectors) < 2:
            return 0.0
        mean_vec = vectors.mean(axis=0)
        return float(np.mean(np.sum((vectors - mean_vec) ** 2, axis=1)))


class NetworkMetrics:
    """Category B: Network structure metrics."""

    def community_structure(self, G: nx.Graph, vectors: np.ndarray, node_list: list[str]) -> dict[str, float]:
        """Modularity and echo chamber index."""
        if G.number_of_nodes() < 3 or G.number_of_edges() == 0:
            return {"modularity": 0.0, "echo_chamber_index": 0.0, "num_communities": 1}

        communities = list(nx.community.greedy_modularity_communities(G))
        modularity = nx.community.modularity(G, communities)

        node_to_idx = {n: i for i, n in enumerate(node_list)}
        community_map = {}
        for idx, comm in enumerate(communities):
            for node in comm:
                community_map[node] = idx

        intra_dists, inter_dists = [], []
        nodes = list(G.nodes())
        for i, a in enumerate(nodes):
            for j, b in enumerate(nodes):
                if i >= j:
                    continue
                if a not in node_to_idx or b not in node_to_idx:
                    continue
                d = np.linalg.norm(vectors[node_to_idx[a]] - vectors[node_to_idx[b]])
                if community_map.get(a) == community_map.get(b):
                    intra_dists.append(d)
                else:
                    inter_dists.append(d)

        eci = 0.0
        if inter_dists and intra_dists:
            mean_inter = np.mean(inter_dists)
            if mean_inter > 1e-10:
                eci = 1.0 - (np.mean(intra_dists) / mean_inter)

        return {
            "modularity": float(modularity),
            "echo_chamber_index": float(eci),
            "num_communities": len(communities),
        }

    def fragmentation(self, G: nx.Graph) -> dict[str, float]:
        """Component-based network fragmentation."""
        if G.number_of_nodes() == 0:
            return {"num_components": 0, "largest_fraction": 0.0, "fragmentation": 0.0}
        components = list(nx.connected_components(G))
        sizes = np.array([len(c) for c in components])
        fractions = sizes / sizes.sum()
        return {
            "num_components": len(components),
            "largest_fraction": float(np.max(fractions)),
            "fragmentation": float(1.0 - np.sum(fractions ** 2)),
        }

    def hub_emergence(self, G: nx.Graph) -> dict[str, float]:
        """Degree centralization and Gini coefficient."""
        if G.number_of_nodes() < 3:
            return {"centralization": 0.0, "gini": 0.0}
        degrees = np.array([d for _, d in G.degree()])
        d_max = degrees.max()
        n = len(degrees)
        centralization = float(np.sum(d_max - degrees) / max((n - 1) * (n - 2), 1))

        sorted_deg = np.sort(degrees).astype(float)
        index = np.arange(1, n + 1)
        total = np.sum(sorted_deg)
        if total == 0:
            gini = 0.0
        else:
            gini = float((2 * np.sum(index * sorted_deg)) / (n * total) - (n + 1) / n)

        return {"centralization": centralization, "gini": gini}

    def small_world(self, G: nx.Graph) -> dict[str, float]:
        """Small-world coefficient (sigma). >1 = small-world property present."""
        if G.number_of_nodes() < 4 or G.number_of_edges() == 0:
            return {"sigma": 0.0, "clustering": 0.0, "avg_path_length": 0.0}

        if nx.is_connected(G):
            Gc = G
        else:
            Gc = G.subgraph(max(nx.connected_components(G), key=len)).copy()

        if Gc.number_of_nodes() < 4:
            return {"sigma": 0.0, "clustering": 0.0, "avg_path_length": 0.0}

        C = nx.average_clustering(Gc)
        L = nx.average_shortest_path_length(Gc)
        n = Gc.number_of_nodes()
        k_avg = 2 * Gc.number_of_edges() / n

        C_rand = k_avg / n if n > 0 else 0
        L_rand = np.log(n) / np.log(max(k_avg, 1.01))

        sigma = 0.0
        if C_rand > 1e-10 and L_rand > 1e-10:
            sigma = (C / C_rand) / (L / L_rand)

        return {"sigma": float(sigma), "clustering": float(C), "avg_path_length": float(L)}

    def algebraic_connectivity(self, G: nx.Graph) -> float:
        """Second-smallest eigenvalue of Laplacian. 0 = disconnected, approaching 0 = near fragmentation."""
        if G.number_of_nodes() < 2 or not nx.is_connected(G):
            return 0.0
        return float(nx.algebraic_connectivity(G))

    def core_periphery(self, G: nx.Graph) -> dict[str, float]:
        """Core-periphery structure score."""
        if G.number_of_nodes() < 4:
            return {"cp_score": 0.0, "core_size": 0}
        A = nx.adjacency_matrix(G).toarray().astype(float)
        n = A.shape[0]
        k_core = max(int(0.3 * n), 2)

        degrees = A.sum(axis=1)
        core_idx = np.argsort(degrees)[-k_core:]

        for _ in range(10):
            core_set = list(core_idx)
            core_connectivity = np.array([A[i, core_set].sum() for i in range(n)])
            core_idx = np.argsort(core_connectivity)[-k_core:]

        periph_idx = np.array([i for i in range(n) if i not in set(core_idx)])
        core_idx = np.array(core_idx)

        cc = A[np.ix_(core_idx, core_idx)].sum() / max(k_core * (k_core - 1), 1)
        pp = A[np.ix_(periph_idx, periph_idx)].sum() / max(len(periph_idx) * (len(periph_idx) - 1), 1)
        cp_score = float(cc - pp)

        return {"cp_score": cp_score, "core_size": k_core}


class PhaseTransitionMetrics:
    """Category D: Phase transition early warning signals."""

    def ar1_coefficient(self, series: list[float], window: int = 20) -> float:
        """Lag-1 autocorrelation. Approaches 1 near critical transitions."""
        if len(series) < window:
            return 0.0
        window_data = np.array(series[-window:])
        if np.std(window_data) < 1e-10:
            return 0.0
        r, _ = pearsonr(window_data[:-1], window_data[1:])
        return float(r) if not np.isnan(r) else 0.0

    def rolling_variance(self, series: list[float], window: int = 20) -> float:
        """Variance over recent window. Increases before transitions."""
        if len(series) < window:
            return 0.0
        return float(np.var(series[-window:]))

    def susceptibility(self, vectors: np.ndarray) -> float:
        """System sensitivity to perturbation. N * trace(Cov). Peaks at transitions."""
        if len(vectors) < 3:
            return 0.0
        N = vectors.shape[0]
        cov = np.cov(vectors.T)
        return float(N * np.trace(cov))

    def flickering(self, mean_history: list[np.ndarray], window: int = 20) -> float:
        """Rate of sign changes in projected mean opinion. High = near bifurcation."""
        if len(mean_history) < window:
            return 0.0
        recent = np.array(mean_history[-window:])
        if recent.shape[1] > 1:
            centered = recent - recent.mean(axis=0)
            _, _, Vt = np.linalg.svd(centered, full_matrices=False)
            projected = centered @ Vt[0]
        else:
            projected = recent[:, 0]
        centered_proj = projected - np.median(projected)
        sign_changes = np.sum(np.diff(np.sign(centered_proj)) != 0)
        return float(sign_changes / (window - 1))

    def skewness_trend(self, vectors: np.ndarray, skew_history: list[float], window: int = 20) -> dict[str, float]:
        """Skewness of opinion distribution and whether it's trending."""
        if len(vectors) < 4:
            return {"skewness": 0.0, "trending": 0.0}
        centered = vectors - vectors.mean(axis=0)
        _, _, Vt = np.linalg.svd(centered, full_matrices=False)
        projected = centered @ Vt[0]
        current_skew = float(skew(projected))

        trending = 0.0
        if len(skew_history) >= window:
            tau, p = kendalltau(np.arange(window), skew_history[-window:])
            if p < 0.05:
                trending = float(tau)

        return {"skewness": current_skew, "trending": trending}

    def susceptibility_peak(self, chi_history: list[float], window: int = 30) -> bool:
        """Detect if susceptibility has peaked recently (phase transition signal)."""
        if len(chi_history) < window:
            return False
        recent = np.array(chi_history[-window:])
        median_chi = np.median(chi_history)
        peaks, _ = find_peaks(recent, height=2 * median_chi, prominence=np.std(recent))
        return len(peaks) > 0


class TemporalMetrics:
    """Category E: Temporal pattern detection."""

    def periodicity(self, series: list[float], min_period: int = 3) -> dict[str, float]:
        """Detect oscillatory behavior via autocorrelation."""
        if len(series) < 30:
            return {"dominant_period": 0.0, "periodicity_strength": 0.0}
        x = np.array(series)
        x = x - x.mean()
        if np.std(x) < 1e-10:
            return {"dominant_period": 0.0, "periodicity_strength": 0.0}
        acf = np.correlate(x, x, mode="full")
        acf = acf[len(acf) // 2:]
        acf = acf / acf[0]
        peaks, props = find_peaks(acf[min_period:], height=0.3)
        if len(peaks) == 0:
            return {"dominant_period": 0.0, "periodicity_strength": 0.0}
        best = peaks[0] + min_period
        return {"dominant_period": float(best), "periodicity_strength": float(acf[best])}

    def burst_detection(self, vectors: np.ndarray, prev_vectors: np.ndarray, activity_history: list[float], window: int = 20) -> dict[str, float]:
        """Detect sudden activity spikes via z-score."""
        delta_norms = np.linalg.norm(vectors - prev_vectors, axis=1)
        activity = float(np.mean(delta_norms))

        z_score = 0.0
        if len(activity_history) >= window:
            w = np.array(activity_history[-window:])
            std = w.std()
            if std > 1e-10:
                z_score = (activity - w.mean()) / std

        return {"activity": activity, "z_score": float(z_score), "is_burst": z_score > 2.5}

    def trend(self, series: list[float], window: int = 30) -> dict[str, float]:
        """Mann-Kendall trend detection. Tau > 0.3 = significant monotonic trend."""
        if len(series) < window:
            return {"tau": 0.0, "p_value": 1.0, "has_trend": False}
        recent = series[-window:]
        tau, p = kendalltau(np.arange(window), recent)
        return {"tau": float(tau), "p_value": float(p), "has_trend": abs(tau) > 0.3 and p < 0.05}


class CollectiveMetrics:
    """Category F: Collective behavior patterns."""

    def herding(self, vector_history: list[np.ndarray], G: nx.Graph, node_list: list[str], window: int = 15) -> float:
        """Fraction of connected pairs showing leader-follower dynamics."""
        if len(vector_history) < window + 1:
            return 0.0
        recent = np.array(vector_history[-window - 1:])
        deltas = np.diff(recent, axis=0)
        delta_norms = np.linalg.norm(deltas, axis=2)

        node_to_idx = {n: i for i, n in enumerate(node_list)}
        herding_count = 0
        total_pairs = 0

        for u, v in G.edges():
            if u not in node_to_idx or v not in node_to_idx:
                continue
            i, j = node_to_idx[u], node_to_idx[v]
            total_pairs += 1
            traj_i = delta_norms[:, i]
            traj_j = delta_norms[:, j]
            if np.std(traj_i) < 1e-10 or np.std(traj_j) < 1e-10:
                continue
            max_rho = 0.0
            for lag in range(1, min(4, window)):
                r = np.corrcoef(traj_i[:-lag], traj_j[lag:])[0, 1]
                if not np.isnan(r):
                    max_rho = max(max_rho, abs(r))
            if max_rho > 0.3:
                herding_count += 1

        return herding_count / max(total_pairs, 1)

    def contrarianism(self, vector_history: list[np.ndarray], window: int = 15) -> dict[str, float]:
        """Fraction of agents systematically opposing majority direction."""
        if len(vector_history) < window + 1:
            return {"contrarian_fraction": 0.0, "contrarian_ids": []}
        recent = np.array(vector_history[-window - 1:])
        deltas = np.diff(recent, axis=0)
        N = deltas.shape[1]

        contrarians = 0
        for i in range(N):
            alignments = []
            for t in range(deltas.shape[0]):
                delta_i = deltas[t, i]
                mean_delta = deltas[t].mean(axis=0)
                norm_i = np.linalg.norm(delta_i)
                norm_m = np.linalg.norm(mean_delta)
                if norm_i > 1e-10 and norm_m > 1e-10:
                    alignments.append(np.dot(delta_i, mean_delta) / (norm_i * norm_m))
            if alignments and np.mean(alignments) < -0.3:
                contrarians += 1

        return {"contrarian_fraction": contrarians / N}

    def free_riding(self, vector_history: list[np.ndarray], interaction_counts: dict[int, int], window: int = 15) -> float:
        """Fraction of agents that interact but don't update beliefs."""
        if len(vector_history) < window + 1:
            return 0.0
        recent = np.array(vector_history[-window - 1:])
        deltas = np.diff(recent, axis=0)
        N = deltas.shape[1]

        mean_activity = np.mean(np.linalg.norm(deltas, axis=2))
        epsilon = 0.1 * mean_activity if mean_activity > 0 else 1e-10

        free_riders = 0
        for i in range(N):
            activity = np.mean(np.linalg.norm(deltas[:, i], axis=1))
            interactions = interaction_counts.get(i, 0)
            if activity < epsilon and interactions > 0:
                free_riders += 1

        return free_riders / N

    def groupthink(self, G: nx.Graph, vectors: np.ndarray, node_list: list[str]) -> float:
        """Diversity collapse within communities relative to population."""
        if G.number_of_nodes() < 4 or G.number_of_edges() == 0:
            return 0.0

        communities = list(nx.community.greedy_modularity_communities(G))
        if len(communities) < 2:
            return 0.0

        node_to_idx = {n: i for i, n in enumerate(node_list)}
        full_dists = pdist(vectors, "euclidean")
        full_diversity = np.mean(full_dists) if len(full_dists) > 0 else 1e-10

        gt_scores = []
        for comm in communities:
            comm_list = [n for n in comm if n in node_to_idx]
            if len(comm_list) < 2:
                continue
            comm_idx = [node_to_idx[n] for n in comm_list]
            comm_vectors = vectors[comm_idx]
            comm_dists = pdist(comm_vectors, "euclidean")
            comm_diversity = np.mean(comm_dists) if len(comm_dists) > 0 else 0.0
            gt = 1.0 - (comm_diversity / max(full_diversity, 1e-10))
            gt_scores.append((len(comm_list), gt))

        if not gt_scores:
            return 0.0
        total = sum(s for s, _ in gt_scores)
        return float(sum(s * gt for s, gt in gt_scores) / total)


class EmergenceDetector:
    """Orchestrates all metric computations and detects emergent phenomena."""

    def __init__(
        self,
        society: AgentSociety,
        config: dict | None = None,
    ):
        self._society = society
        cfg = config or {}
        self._thresholds = {
            "consensus": cfg.get("consensus_threshold", 0.9),
            "polarization_bc": cfg.get("polarization_threshold", 0.555),
            "fragmentation_enp": cfg.get("fragmentation_threshold", 2.5),
            "modularity": cfg.get("modularity_threshold", 0.3),
            "echo_chamber": cfg.get("echo_chamber_threshold", 0.5),
            "ar1_critical": cfg.get("ar1_threshold", 0.85),
            "burst_z": cfg.get("burst_z_threshold", 2.5),
            "groupthink": cfg.get("groupthink_threshold", 0.7),
        }
        self._store = TimeSeriesStore()
        self._opinion = OpinionMetrics()
        self._network = NetworkMetrics()
        self._phase = PhaseTransitionMetrics()
        self._temporal = TemporalMetrics()
        self._collective = CollectiveMetrics()
        self._events: list[EmergenceEvent] = []
        self._mean_history: list[np.ndarray] = []
        self._tick = 0

    def on_tick(self, tick: int, tick_result: TickResult) -> None:
        """Tick callback — registered on SimulationEngine."""
        self._tick = tick
        states = self._society.get_all_states()
        agent_ids = list(states.keys())
        vectors = np.array([states[aid].vector for aid in agent_ids])

        self._store.record_vectors(vectors)
        self._mean_history.append(vectors.mean(axis=0))

        self._compute_every_tick(vectors, agent_ids)

        if tick > 0 and tick % 5 == 0:
            self._compute_every_5_ticks(vectors, agent_ids)

        if tick > 0 and tick % 10 == 0:
            self._compute_every_10_ticks(vectors, agent_ids)

        self._detect_events(tick, vectors)

    def _compute_every_tick(self, vectors: np.ndarray, agent_ids: list[str]) -> None:
        self._store.record_metric("consensus", self._opinion.consensus(vectors))
        self._store.record_metric("variance", self._opinion.variance(vectors))
        self._store.record_metric("diameter", self._opinion.diameter(vectors))
        self._store.record_metric("polarization_bc", self._opinion.polarization(vectors))

        ext = self._opinion.extremization(vectors)
        self._store.record_metric("extremism_index", ext["extremism_index"])

        self._store.record_metric("susceptibility", self._phase.susceptibility(vectors))

        var_hist = self._store.get("variance")
        self._store.record_metric("convergence_rate", self._opinion.convergence_rate(var_hist))
        self._store.record_metric("ar1", self._phase.ar1_coefficient(var_hist))
        self._store.record_metric("rolling_var", self._phase.rolling_variance(var_hist))

        if len(self._mean_history) >= 20:
            self._store.record_metric("flickering", self._phase.flickering(self._mean_history))

        skew_hist = self._store.get("skewness")
        skew_result = self._phase.skewness_trend(vectors, skew_hist)
        self._store.record_metric("skewness", skew_result["skewness"])

        if self._store.tick_count > 1:
            prev = self._store.get_vectors()[-2]
            burst = self._temporal.burst_detection(vectors, prev, self._store.get("activity"))
            self._store.record_metric("activity", burst["activity"])
            self._store.record_metric("burst_z", burst["z_score"])

    def _compute_every_5_ticks(self, vectors: np.ndarray, agent_ids: list[str]) -> None:
        G = self._build_communication_graph(agent_ids)

        comm = self._network.community_structure(G, vectors, agent_ids)
        self._store.record_metric("modularity", comm["modularity"])
        self._store.record_metric("echo_chamber_index", comm["echo_chamber_index"])

        frag = self._network.fragmentation(G)
        self._store.record_metric("net_fragmentation", frag["fragmentation"])
        self._store.record_metric("num_components", frag["num_components"])

        hub = self._network.hub_emergence(G)
        self._store.record_metric("centralization", hub["centralization"])
        self._store.record_metric("gini", hub["gini"])

        self._store.record_metric("algebraic_connectivity", self._network.algebraic_connectivity(G))

        gt = self._collective.groupthink(G, vectors, agent_ids)
        self._store.record_metric("groupthink", gt)

        contr = self._collective.contrarianism(self._store.get_vectors())
        self._store.record_metric("contrarian_fraction", contr["contrarian_fraction"])

        var_hist = self._store.get("variance")
        trend = self._temporal.trend(var_hist)
        self._store.record_metric("variance_trend_tau", trend["tau"])

    def _compute_every_10_ticks(self, vectors: np.ndarray, agent_ids: list[str]) -> None:
        G = self._build_communication_graph(agent_ids)

        sw = self._network.small_world(G)
        self._store.record_metric("small_world_sigma", sw["sigma"])

        cp = self._network.core_periphery(G)
        self._store.record_metric("core_periphery_score", cp["cp_score"])

        herding = self._collective.herding(self._store.get_vectors(), G, agent_ids)
        self._store.record_metric("herding_index", herding)

        var_hist = self._store.get("variance")
        period = self._temporal.periodicity(var_hist)
        self._store.record_metric("dominant_period", period["dominant_period"])
        self._store.record_metric("periodicity_strength", period["periodicity_strength"])

    def _detect_events(self, tick: int, vectors: np.ndarray) -> None:
        consensus = self._store.get("consensus")[-1] if self._store.get("consensus") else 0
        if consensus > self._thresholds["consensus"]:
            self._emit(tick, "consensus", consensus, f"Consensus reached (score={consensus:.3f})")

        bc = self._store.get("polarization_bc")[-1] if self._store.get("polarization_bc") else 0
        if bc > self._thresholds["polarization_bc"]:
            self._emit(tick, "polarization", bc, f"Polarization detected (BC={bc:.3f})")

        frag = self._store.get("net_fragmentation")
        if frag and frag[-1] > 0.3:
            self._emit(tick, "network_fragmentation", frag[-1], f"Network fragmenting ({frag[-1]:.3f})")

        mod = self._store.get("modularity")
        eci = self._store.get("echo_chamber_index")
        if mod and eci and mod[-1] > self._thresholds["modularity"] and eci[-1] > self._thresholds["echo_chamber"]:
            self._emit(tick, "echo_chambers", eci[-1], f"Echo chambers forming (ECI={eci[-1]:.3f})")

        ar1 = self._store.get("ar1")[-1] if self._store.get("ar1") else 0
        if ar1 > self._thresholds["ar1_critical"]:
            self._emit(tick, "critical_slowing_down", ar1, f"Critical slowing down (AR1={ar1:.3f})")

        burst_z = self._store.get("burst_z")[-1] if self._store.get("burst_z") else 0
        if burst_z > self._thresholds["burst_z"]:
            self._emit(tick, "burst", burst_z, f"Activity burst detected (z={burst_z:.2f})")

        gt = self._store.get("groupthink")[-1] if self._store.get("groupthink") else 0
        if gt > self._thresholds["groupthink"]:
            self._emit(tick, "groupthink", gt, f"Groupthink detected (score={gt:.3f})")

        chi_hist = self._store.get("susceptibility")
        if self._phase.susceptibility_peak(chi_hist):
            self._emit(tick, "phase_transition", chi_hist[-1], "Susceptibility peak — possible phase transition")

    def _emit(self, tick: int, event_type: str, confidence: float, description: str) -> None:
        if self._events and self._events[-1].event_type == event_type and self._events[-1].tick >= tick - 2:
            return
        self._events.append(EmergenceEvent(
            event_type=event_type,
            tick=tick,
            confidence=min(confidence, 1.0),
            metrics=self._current_metrics(),
            description=description,
        ))

    def _current_metrics(self) -> dict[str, float]:
        result = {}
        for name, series in self._store.all_metrics.items():
            if series:
                result[name] = series[-1]
        return result

    def _build_communication_graph(self, agent_ids: list[str]) -> nx.Graph:
        """Build undirected graph from active COMMUNICATES_WITH edges."""
        G = nx.Graph()
        G.add_nodes_from(agent_ids)
        graph = self._society._graph
        for aid in agent_ids:
            rels = graph.get_relationships(aid, direction="out", rel_type="COMMUNICATES_WITH")
            for rel in rels:
                if rel.valid_to is None and rel.target_id in G:
                    G.add_edge(rel.source_id, rel.target_id)
        return G

    @property
    def events(self) -> list[EmergenceEvent]:
        return self._events.copy()

    @property
    def metric_history(self) -> dict[str, list[float]]:
        return self._store.all_metrics
