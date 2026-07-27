"""Geometry for strike localization: local ENU projection, range rings,
multilateration from flash-to-bang ranges, and uncertainty ellipses.

Same flat-earth projection as scripts/tdoa_sim.py — fine at the <50 km scales
FlashPoint works at.
"""
import math

import numpy as np

M_PER_DEG_LAT = 110_540.0
M_PER_DEG_LON_EQ = 111_320.0


def to_xy(lat, lon, lat0, lon0):
    """(lat, lon) -> local east/north meters around (lat0, lon0)."""
    x = (lon - lon0) * M_PER_DEG_LON_EQ * math.cos(math.radians(lat0))
    y = (lat - lat0) * M_PER_DEG_LAT
    return x, y


def to_latlon(x, y, lat0, lon0):
    lat = lat0 + y / M_PER_DEG_LAT
    lon = lon0 + x / (M_PER_DEG_LON_EQ * math.cos(math.radians(lat0)))
    return lat, lon


def dist_km(lat1, lon1, lat2, lon2):
    x, y = to_xy(lat2, lon2, lat1, lon1)
    return math.hypot(x, y) / 1000.0


def ring_path(lat, lon, radius_m, n=120):
    """Circle of radius_m around (lat, lon) as [[lon, lat], ...] for pydeck PathLayer."""
    pts = []
    for k in range(n + 1):
        a = 2 * math.pi * k / n
        la, lo = to_latlon(radius_m * math.sin(a), radius_m * math.cos(a), lat, lon)
        pts.append([lo, la])
    return pts


def ellipse_polygon(lat, lon, semi_major_m, semi_minor_m, angle_deg, n=72):
    """Uncertainty ellipse as [[lon, lat], ...]; angle_deg = major axis from east, CCW."""
    ca, sa = math.cos(math.radians(angle_deg)), math.sin(math.radians(angle_deg))
    pts = []
    for k in range(n + 1):
        t = 2 * math.pi * k / n
        ex, ey = semi_major_m * math.cos(t), semi_minor_m * math.sin(t)
        x, y = ex * ca - ey * sa, ex * sa + ey * ca
        la, lo = to_latlon(x, y, lat, lon)
        pts.append([lo, la])
    return pts


def _residuals(p, anchors, ranges):
    d = np.hypot(anchors[:, 0] - p[0], anchors[:, 1] - p[1])
    return d - ranges


def trilaterate(anchors_xy, ranges_m, sigmas_m):
    """Least-squares intersection of range circles (Gauss-Newton, multistart).

    anchors_xy: (n, 2) node positions in local meters
    ranges_m:   (n,) flash-to-bang ranges
    sigmas_m:   (n,) 1-sigma range uncertainties

    Returns dict with the estimate, 1-sigma uncertainty ellipse, rms residual,
    and a GDOP-style conditioning number — or None when n < 2.
    With n == 2 the problem is bimodal; both circle intersections are returned
    in `alternates` and the better-conditioned one is the estimate.
    """
    A = np.asarray(anchors_xy, float)
    r = np.asarray(ranges_m, float)
    s = np.maximum(np.asarray(sigmas_m, float), 1.0)
    n = len(A)
    if n < 2:
        return None
    w = 1.0 / s

    def refine(p0):
        p = np.array(p0, float)
        for _ in range(60):
            d = np.hypot(A[:, 0] - p[0], A[:, 1] - p[1])
            d = np.maximum(d, 1e-6)
            J = np.stack([(p[0] - A[:, 0]) / d, (p[1] - A[:, 1]) / d], axis=1)
            res = (d - r) * w
            Jw = J * w[:, None]
            try:
                step, *_ = np.linalg.lstsq(Jw, -res, rcond=None)
            except np.linalg.LinAlgError:
                return None
            p = p + step
            if np.linalg.norm(step) < 0.01:
                break
        return p

    # multistart: circle-pair intersections + centroid, keep best weighted cost
    starts = [A.mean(axis=0)]
    for i in range(n):
        for j in range(i + 1, n):
            starts.extend(_circle_intersections(A[i], r[i], A[j], r[j]))
    best, alternates = None, []
    for p0 in starts:
        p = refine(p0)
        if p is None or not np.all(np.isfinite(p)):
            continue
        cost = float(np.sum((_residuals(p, A, r) * w) ** 2))
        if not any(np.linalg.norm(p - q["xy"]) < 50 for q in alternates):
            alternates.append({"xy": p, "cost": cost})
    if not alternates:
        return None
    alternates.sort(key=lambda q: q["cost"])
    best = alternates[0]
    p = best["xy"]

    # covariance + GDOP from the weighted Jacobian at the solution
    d = np.maximum(np.hypot(A[:, 0] - p[0], A[:, 1] - p[1]), 1e-6)
    J = np.stack([(p[0] - A[:, 0]) / d, (p[1] - A[:, 1]) / d], axis=1)
    Jw = J * w[:, None]
    JtJ = Jw.T @ Jw

    # Geometry conditioning. A rank-deficient normal matrix (two rings from the
    # same node, or a fully collinear set) has a near-zero eigenvalue; the
    # solution is unconstrained along that axis. Using pinv here would HIDE that
    # (it drops the null eigenvalue and reports a small, "good" GDOP), so detect
    # degeneracy explicitly and report it honestly instead of inventing numbers.
    unit_evals = np.linalg.eigvalsh(J.T @ J)  # DOP from unit-weight geometry
    degenerate = unit_evals.min() <= unit_evals.max() * 1e-9
    gdop = float("inf") if degenerate else float(np.sqrt(np.sum(1.0 / unit_evals)))

    dof = max(n - 2, 1)
    res = _residuals(p, A, r) * w
    scale = max(float(res @ res) / dof, 1.0) if n > 2 else 1.0
    if degenerate:
        semi_major = semi_minor = float("inf")
        angle = 0.0
    else:
        cov = np.linalg.inv(JtJ) * scale
        evals, evecs = np.linalg.eigh(cov)
        evals = np.maximum(evals, 0.0)
        semi_minor, semi_major = (float(np.sqrt(evals[0])), float(np.sqrt(evals[1])))
        angle = math.degrees(math.atan2(evecs[1, 1], evecs[0, 1]))
    rms = float(np.sqrt(np.mean(_residuals(p, A, r) ** 2)))

    # Bimodal = the runner-up solution is (near-)tied with the best. True for
    # 2-ring fixes, but also for 3+ near-collinear anchors with a mirror image.
    runner = alternates[1]["cost"] if len(alternates) > 1 else None
    bimodal = n == 2 or (
        runner is not None and runner <= best["cost"] + max(1.0, 0.05 * best["cost"]))

    return {
        "xy": (float(p[0]), float(p[1])),
        "semi_major_m": semi_major,
        "semi_minor_m": semi_minor,
        "angle_deg": angle,
        "rms_m": rms,
        "gdop": gdop,
        "n_nodes": n,
        "bimodal": bool(bimodal),
        "degenerate": bool(degenerate),
        "alternates": [(float(q["xy"][0]), float(q["xy"][1])) for q in alternates[1:3]],
    }


def _circle_intersections(c1, r1, c2, r2):
    """Intersection points of two circles (or closest-approach point when disjoint)."""
    c1, c2 = np.asarray(c1, float), np.asarray(c2, float)
    d = float(np.linalg.norm(c2 - c1))
    if d < 1e-9:
        return []
    u = (c2 - c1) / d
    a = (d * d + r1 * r1 - r2 * r2) / (2 * d)
    h2 = r1 * r1 - a * a
    mid = c1 + a * u
    if h2 <= 0:
        return [mid]  # circles don't cross: start from the closest-approach point
    h = math.sqrt(h2)
    perp = np.array([-u[1], u[0]])
    return [mid + h * perp, mid - h * perp]
