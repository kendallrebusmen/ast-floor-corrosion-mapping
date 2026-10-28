"""Phase 2: reconcile the two inspections' plate numbering schemes.

Working hypothesis (from the layout drawings): both vendors used the same
serpentine numbering. This module tests that hypothesis quantitatively by
scoring the identity mapping against the alternative plate permutations
induced by the 8 dihedral symmetries of the layout (rotations by 180°,
east-west and north-south mirrors, and transposed variants), using
per-plate anomaly-density rank correlation between the inspections.
"""
import math

# the 8 dihedral transforms of the plane: (name, fn(x, y) -> (x', y'))
_TRANSFORMS = [
    ("identity", lambda x, y: (x, y)),
    ("mirror_x", lambda x, y: (-x, y)),      # east-west flip
    ("mirror_y", lambda x, y: (x, -y)),      # north-south flip
    ("rot180", lambda x, y: (-x, -y)),
    ("transpose", lambda x, y: (y, x)),
    ("rot90", lambda x, y: (-y, x)),
    ("rot270", lambda x, y: (y, -x)),
    ("anti_transpose", lambda x, y: (-y, -x)),
]


def symmetry_mappings(centers):
    """Candidate plate permutations from layout symmetries.

    centers: {plate: (x, y)} plate centers in tank inches (origin at tank
    center). Returns {transform_name: {plate: mapped_plate}} where each
    plate maps to the plate whose center is nearest its transformed center.
    """
    out = {}
    for name, fn in _TRANSFORMS:
        mapping = {}
        for p, (x, y) in centers.items():
            tx, ty = fn(x, y)
            mapping[p] = min(
                centers,
                key=lambda q: (centers[q][0] - tx) ** 2 + (centers[q][1] - ty) ** 2,
            )
        out[name] = mapping
    return out


def spearman(xs, ys):
    """Spearman rank correlation (no scipy dependency at import time)."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx) / len(rx)
    my = sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    dy = math.sqrt(sum((b - my) ** 2 for b in ry))
    return num / (dx * dy) if dx and dy else 0.0


def score_mappings(centers, counts_a, counts_b):
    """Rank-correlate per-plate densities under each candidate mapping.

    counts_a / counts_b: {plate: anomaly count} for inspections A and B.
    Returns [(name, spearman_r)] sorted best-first.
    """
    plates = sorted(centers)
    results = []
    for name, mapping in symmetry_mappings(centers).items():
        xs = [counts_a.get(p, 0) for p in plates]
        ys = [counts_b.get(mapping[p], 0) for p in plates]
        results.append((name, spearman(xs, ys)))
    return sorted(results, key=lambda t: -t[1])
