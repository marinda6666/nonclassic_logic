"""Deterministic hard clustering of fuzzy quantities, with NumPy acceleration."""
import numpy as np
from .fuzzy import EPS, check, feature


def analyze(items, options=None):
    options = options or {}
    check(2 <= len(items) <= 500, 'Для анализа требуется от 2 до 500 величин.')
    metric, mode = options.get('metric', 'cuts'), options.get('mode', 'fixed')
    alpha = options.get('alpha', .5)
    check(type(alpha) in (int, float) and np.isfinite(alpha) and EPS <= alpha <= 1,
          'Уровень α должен быть от 0,000001 до 1.')
    x = np.array([feature(v, metric, alpha) for v in items], dtype=float)
    n, dim = x.shape
    distances = np.empty((n, n))
    for i in range(n):
        distances[i] = np.sqrt(np.mean((x - x[i]) ** 2, axis=1))
    converged = True
    if mode == 'threshold':
        threshold = options.get('threshold')
        check(isinstance(threshold, (float, int)) and np.isfinite(threshold) and threshold >= 0, 'Порог должен быть неотрицательным числом.')
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(n):
            for j in range(i + 1, n):
                if distances[i, j] <= threshold:
                    parent[find(j)] = find(i)
        roots = {}
        labels = np.array([roots.setdefault(find(i), len(roots)) for i in range(n)])
        iterations = 1
    else:
        check(mode == 'fixed', 'Неизвестный режим.')
        k = options.get('k', 3)
        check(type(k) is int and 1 <= k <= min(10, n), 'Число кластеров: от 1 до min(10, N).')
        chosen = [0]
        while len(chosen) < k:
            nearest = np.min(distances[:, chosen], axis=1)
            nearest[chosen] = -1
            chosen.append(int(np.argmax(nearest)))
        centers, labels = x[chosen].copy(), np.full(n, -1)
        converged = False
        for iterations in range(1, 101):
            costs = np.mean((x[:, None, :] - centers[None, :, :]) ** 2, axis=2)
            next_labels = np.argmin(costs, axis=1)
            counts = np.bincount(next_labels, minlength=k)
            for c in range(k):
                if counts[c] == 0:
                    errors = costs[np.arange(n), next_labels].copy()
                    errors[counts[next_labels] <= 1] = -1
                    far = int(np.argmax(errors))
                    counts[next_labels[far]] -= 1
                    next_labels[far] = c
                    counts[c] += 1
            stable = np.array_equal(labels, next_labels)
            labels = next_labels
            centers = np.array([x[labels == c].mean(axis=0) for c in range(k)])
            if stable:
                converged = True
                break
    k = int(labels.max()) + 1
    groups = [np.flatnonzero(labels == c).tolist() for c in range(k)]
    centers = np.array([x[g].mean(axis=0) for g in groups])
    inertia = float(np.mean((x - centers[labels]) ** 2, axis=1).sum())
    silhouette = None
    if 1 < k < n:
        scores = []
        for i in range(n):
            g = groups[int(labels[i])]
            if len(g) == 1:
                scores.append(0)
                continue
            a = float(distances[i, g].sum() / (len(g) - 1))
            b = min(float(distances[i, h].mean()) for c, h in enumerate(groups) if c != labels[i])
            scores.append((b - a) / max(a, b) if max(a, b) > 0 else 0)
        silhouette = float(np.mean(scores))
    return dict(labels=labels.tolist(), groups=groups, centers=centers.tolist(), inertia=inertia,
                silhouette=silhouette, iterations=iterations, converged=converged,
                metric=metric, alpha=alpha, mode=mode,
                threshold=options.get('threshold') if mode == 'threshold' else None)
