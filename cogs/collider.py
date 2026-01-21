#!/usr/bin/env python3
from __future__ import annotations

import io
import math
import os
import random
import tempfile
from time import perf_counter
from typing import Any

import numpy as np
import pythia8mc as p8
import matplotlib


matplotlib.use("Agg")   # safest default on Linux if Tk is installed

from matplotlib import pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter, PillowWriter


def _pdg_name(pythia, pid: int) -> str:
    # robust: particleData.name exists in most bindings
    try:
        return str(pythia.particleData.name(pid))
    except Exception:
        return str(pid)
    
def status_stage(status: int) -> str:
    a = abs(int(status))
    i = a // 10
    j = a % 10

    if 11 <= a <= 19:
        return "BEAM"
    if a == 21:
        return "HARD-IN"
    if a in [23, 24]:
        return "HARD-OUT"
    if 21 <= a <= 29:
        return "HARD"
    if a in [31, 34]:
        return "MPI-IN"
    if a in [33]:
        return "MPI-OUT"
    if 31 <= a <= 39:
        return "MPI"
    if a in [41, 42, 45, 46]:
        return "ISR-IN"
    if a in [43, 44]:
        return "ISR-OUT"
    if 41 <= a <= 49:
        return "ISR"
    if a in [53, 54]:
        return "FSR-IN"
    if a == 51:
        return "FSR-OUT"
    if 51 <= a <= 59:
        return "FSR"
    if 61 == a:
        return "REMN-IN"
    if 62 == a:
        return "REMN-OUT-COPY"
    if 63 == a:
        return "REMN-OUT"
    if 64 <= a <= 69:
        return "REMN"
    if 71 <= a <= 79:
        return "HADPREP"
    if 81 <= a <= 89:
        return "HAD"
    if 91 <= a <= 99:
        return "DECAY"
    if i >= 20:
        return "USER"
    return "OTHER"

    
def desc(p, *, show_moms=True, show_kids=True, show_kin=True, show_vtx=True, show_col=False) -> str:
    idx = p.index()
    pid = p.id()
    st  = p.status()
    stage = status_stage(st)

    parts = [f"idx={idx:4d} id={pid:6d} {p.nameWithStatus():<22} st={st:4d} [{stage}]"]

    # Mothers/daughters
    if show_moms:
        moms = list(p.motherList())
        if moms:
            parts.append(f"moms={moms}")
        else:
            parts.append("moms=[]")

    if show_kids:
        kids = list(p.daughterList())
        if kids:
            # compact: show list if short, else show range + count
            if len(kids) <= 10:
                parts.append(f"kids={kids}")
            else:
                parts.append(f"kids=[{kids[0]}..{kids[-1]}] n={len(kids)}")
        else:
            parts.append("kids=[]")

    # Kinematics
    if show_kin:
        px, py, pz, e = p.px(), p.py(), p.pz(), p.e()
        pt = math.hypot(px, py)
        pabs = math.sqrt(px*px + py*py + pz*pz)
        eta = p.eta() if hasattr(p, "eta") else float("nan")
        parts.append(f"pT={pt:7.2f} p={pabs:7.2f} eta={eta:6.2f} E={e:7.2f}")

    # Vertex (production)
    if show_vtx:
        # in Pythia event record, xProd/yProd/zProd are usually in mm
        parts.append(f"vtx(mm)=({p.xProd():7.2f},{p.yProd():7.2f},{p.zProd():7.2f})")

    # Color tags
    if show_col:
        parts.append(f"col=({p.col()},{p.acol()})")

    return "  ".join(parts)


def marker(p) -> str:
    st = abs(int(p.status()))
    if st == 23:
        return " <HARD-OUT>"
    if st == 33:
        return " <MPI-OUT>"
    if st == 63:
        return " <REMNANT>"
    if 81 <= st <= 89:
        return " <HADRON>"
    if 91 <= st <= 99:
        return " <DECAY>"
    return ""

def print_tree(
    evt,
    root_idx: int,
    *,
    max_depth: int = 6,
    max_nodes: int = 400,
    show_moms: bool = True,
    show_kids: bool = True,
    show_kin: bool = True,
    show_vtx: bool = True,
    show_col: bool = False,
    # filter: if provided, only print nodes where predicate(p) is True,
    # but still traverse through all children so you don't break the tree.
    only_if=None,
):
    seen = set()
    stack = [(root_idx, 0)]
    n = 0
    while stack and n < max_nodes:
        idx, d = stack.pop()
        if idx in seen:
            continue
        seen.add(idx)
        p = evt[idx]

        # print line?
        if (only_if is None) or only_if(p):
            print("  " * d + desc(
                p,
                show_moms=show_moms,
                show_kids=show_kids,
                show_kin=show_kin,
                show_vtx=show_vtx,
                show_col=show_col,
            ) + marker(p))
            n += 1

        if d >= max_depth:
            continue

        kids = list(p.daughterList())
        # small indices first in DFS output
        for k in reversed(kids):
            stack.append((k, d + 1))
            
            
def pid_to_short(pid: int) -> str:
    return {
        21: "g",
        1: "d", -1: "dbar",
        2: "u", -2: "ubar",
        3: "s", -3: "sbar",
        4: "c", -4: "cbar",
        5: "b", -5: "bbar",
        6: "t", -6: "tbar",
        22: "γ",
        11: "e-", -11: "e+",
        13: "μ-", -13: "μ+",
        12: "νe", -12: "νebar",
        14: "νμ", -14: "νμbar",
        16: "ντ", -16: "ντbar",
    }.get(pid, str(pid))

def summarize_event(pythia: p8.Pythia) -> str:
    info = pythia.infoPython()

    # 1) Hardest process headline from Pythia itself
    hard_name = info.name()          # often "g g -> g g" etc
    pthat = info.pTHat()

    # 2) Summarize MPI scatters by looking at MPI outgoing legs
    evt = pythia.event
    mpi_out = [p for p in evt if abs(int(p.status())) == 33]

    # Group MPI outgoing particles by their mothers (the incoming pair)
    scatters = {}
    for p in mpi_out:
        moms = tuple(sorted(list(p.motherList())))
        if len(moms) != 2:
            continue
        scatters.setdefault(moms, []).append(p.index())

    mpi_lines = []
    for moms, outs in scatters.items():
        a, b = moms
        pa, pb = evt[a], evt[b]
        # incoming types
        in_a = pid_to_short(int(pa.id()))
        in_b = pid_to_short(int(pb.id()))
        # outgoing types (take first two if present)
        out_pids = [pid_to_short(int(evt[i].id())) for i in outs[:2]]
        if len(out_pids) == 2:
            mpi_lines.append(f"{in_a} {in_b} → {out_pids[0]} {out_pids[1]}")
        else:
            mpi_lines.append(f"{in_a} {in_b} → ...")

    n_mpi = info.nMPI()
    n_isr = info.nISR()
    n_fsr = info.nFSRinProc()

    # Compose
    s = f"Hard: {hard_name} (pTHat={pthat:.1f} GeV)"
    if mpi_lines:
        # Note: info.nMPI() counts interactions; your mpi_lines counts distinct mother-pairs seen.
        s += f"\nMPI: {len(mpi_lines)} scatter(s): " + "; ".join(mpi_lines)
    else:
        s += f"\nMPI: none found in record"
    s += f"\nActivity: nMPI={n_mpi}, nISR={n_isr}, nFSR={n_fsr}"
    return s



NAME_TO_PID = {
    "pi+": 211,
    "pi-": -211,
    "K+": 321,
    "K-": -321,
    "p": 2212,
    "pbar": -2212,
    "e-": 11,
    "e+": -11,
    "mu-": 13,
    "mu+": -13,
    "gamma": 22,
    "nu_e": 12,
    "nu_ebar": -12,
    "nu_mu": 14,
    "nu_mubar": -14,
    "nu_tau": 16,
    "nu_taubar": -16,
    
    # alternative names
    "e": 11,
    "mu": 13,
    "photon": 22,
    "nu": 12,
    "neutrino": 12,
}

PID_LABEL = {
    # charged basic hadrons
    211:  "π+",
    -211: "π−",
    321:  "K+",
    -321: "K−",
    2212: "p",
    -2212:"p̄",
    
    # netural hadrons
    111: "π0",
    130: "K0L",
    310: "K0S",
    2112: "n",
    -2112: "n̄",
    
    # charged leptons
    11:   "e−",
    -11:  "e+",
    13:   "μ−",
    -13:  "μ+",
    
    # photon
    22:   "γ",
    
    # neutrinos
    12:   "νe",
    -12:  "ν̄e",
    14:   "νμ",
    -14:  "ν̄μ",
    16:   "ντ",
    -16:  "ν̄τ",
}

POSITIVE_PARTICLES = (211, 321, 2212, -13, -11)
NEGATIVE_PARTICLES = (-211, -321, -2212, 11, 13)
NEUTRAL_PARTICLES = (111, 130, 310, 2112, -2112, 22, 12, -12, 14, -14, 16, -16)


def color_for_pid(id: int) -> str:
    # if neutrino, purple:
    if is_neutrino(id):
        return "purple"
    
    # elif photon, yellow:
    if id == 22:
        return "gold"
    
    # neutral is grey
    if id in NEUTRAL_PARTICLES:
        return "gray"
    
    elif id in POSITIVE_PARTICLES:
        return "tab:red"
    else:
        return "tab:blue"


def is_neutrino(pid: int) -> bool:
    return abs(pid) in (12, 14, 16, 18)

def make_counts_lines(particle_count: dict[int, int]) -> list[tuple[str, str]]:
    # returns [(line_text, color), ...]
    items = sorted(particle_count.items(), key=lambda kv: kv[1], reverse=True)

    lines: list[tuple[str, str]] = []
    total = 0
    for pid, n in items:
        total += n
        name = PID_LABEL.get(pid, str(pid))

        # Choose a color for that PID (your function can ignore q if you want)
        # For example: use charge sign if known, otherwise neutral color.
        # If you want: infer q_raw from PDG charge (see note below).
        col = color_for_pid(pid)  # implement this

        lines.append((f"{name}: {n}", col))

    lines.append((f"Total: {total}", "k"))
    return lines


def _helix_points_from_momentum(
    x0: float,
    y0: float,
    z0: float,
    px: float,
    py: float,
    pz: float,
    q_raw: int,
    B_T: float,
    R_det_m: float,
    Z_det_m: float,
    n_steps: int,
    s_max: float,
):
    """
    Returns (x,y,z) arrays for a helix segment clipped to a detector cylinder,
    or None if it never enters the volume.

    Assumes:
      - uniform solenoid B along +z
      - q_raw from Pythia is in units of (e/3); convert to q_e = q_raw/3
      - curvature radius R[m] = pT[GeV]/(0.3 * |q_e| * B[T])
    """
    q_e = q_raw / 3.0
    if abs(q_e) < 1e-12:
        return None

    pt = math.hypot(px, py)
    p_tot = math.sqrt(px * px + py * py + pz * pz)
    if pt < 1e-12 or p_tot < 1e-12:
        return None

    # Radius of curvature in meters
    R = pt / (0.3 * abs(q_e) * B_T) if B_T != 0 else 1e12

    # Rotation direction: sign(q * B)
    sgn = 1.0 if (q_e * B_T) > 0 else -1.0
    phi0 = math.atan2(py, px)

    s = np.linspace(0.0, s_max, n_steps)
    phi = s / R
    
    x = x0 + sgn * R * (np.sin(phi0 + sgn * phi) - np.sin(phi0))
    y = y0 - sgn * R * (np.cos(phi0 + sgn * phi) - np.cos(phi0))
    z = z0 + (pz / p_tot) * s

    r_xy = np.sqrt(x * x + y * y)
    inside = (r_xy <= R_det_m) & (np.abs(z) <= Z_det_m)
    idx = np.flatnonzero(inside)  # indices where you're inside cylinder
    if idx.size == 0:
        return None
    
    start = idx[0]  # first index inside cylinder, should basically always be 0 (first index)
    after = inside[start:]  # boolean array starting from first point inside cylinder
    exit_rel = np.flatnonzero(~after)  # ~after is bitwise NOT on the array, flips true/false
    end = (start + exit_rel[0]) if exit_rel.size else len(inside)
    
    return x[start:end], y[start:end], z[start:end]


def _ray_points_from_momentum(
    x0: float,
    y0: float,
    z0: float,
    px: float,
    py: float,
    pz: float,
    R_det_m: float,
    Z_det_m: float,
    n_steps: int,
):
    """Straight-line ray from origin, clipped to a detector cylinder."""
    p_tot = math.sqrt(px * px + py * py + pz * pz)
    if p_tot < 1e-12:
        return None

    ux, uy, uz = px / p_tot, py / p_tot, pz / p_tot

    # Find max t such that (x,y,z) stays within cylinder:
    # r = t*sqrt(ux^2+uy^2) <= R_det, |z| = |t*uz| <= Z_det
    uT = math.hypot(ux, uy)

    t_r = (R_det_m / uT) if uT > 1e-12 else float("inf")
    t_z = (Z_det_m / abs(uz)) if abs(uz) > 1e-12 else float("inf")
    t_max = min(t_r, t_z)
    if not math.isfinite(t_max) or t_max <= 0:
        return None

    t = np.linspace(0.0, t_max, n_steps)
    x = x0 + t * ux
    y = y0 + t * uy
    z = z0 + t * uz
    inside = (np.sqrt(x * x + y * y) <= R_det_m) & (np.abs(z) <= Z_det_m)
    if not np.any(inside):
        return None
    
    return x, y, z


def run_events(
    n_events: int = 10_000,
    ecm_gev: float = 13_000.0,
    p1: str = "2212",
    p2: str = "2212",
    process=None,
    pthat_min_gev: float = 30.0,
    seed: int = 0,
    keep_neutrinos: bool = True,
) -> dict[str, Any]:
    if process is None:
        process = ["HardQCD:all = on"]
    pythia = p8.Pythia()
    
    # disable printing of stats
    # pythia.readString("Next:numberShowEvent = 0")  # no. of events to show event record for (list of all interactions)
    # pythia.readString("Next:numberShowInfo = 0")  # shows summary of collision type
    # pythia.readString("Next:numberShowProcess = 0")  # shows main initial collision
    pythia.readString("Next:showMothersAndDaughters = on")
    
    # Suppress init-time printouts (banner, process init tables, etc.)
    # pythia.readString("Init:showAllSettings = off")
    # pythia.readString("Init:showChangedSettings = off")
    # pythia.readString("Init:showAllParticleData = off")
    # pythia.readString("Init:showChangedParticleData = off")
    # pythia.readString("Init:showProcesses = off")  # show enabled processes and cross sections
    # pythia.readString("Init:showMultipartonInteractions = off")
    
    # enable HadronDecay
    pythia.readString("HadronLevel:Decay = on")
    
    # Settings
    pythia.readString(f"Beams:idA = {p1}")
    pythia.readString(f"Beams:idB = {p2}")
    pythia.readString(f"Beams:eCM = {ecm_gev}")
    
    for process_line in process:
        pythia.readString(process_line)
  
    pythia.readString(f"PhaseSpace:pTHatMin = {pthat_min_gev}")
    
    pythia.readString("Random:setSeed = on")
    if not seed:
        seed = random.randint(1, 900_000_000)
    pythia.readString(f"Random:seed = {seed}")
    
    try:
        seed_val = pythia.settings.mode("Random:seed")
        print("Random:seed =", seed_val)
    except Exception as e:
        print("Could not read Random:seed via settings.mode:", e)
    
    # Beam spot / primary vertex smearing (units: mm)
    pythia.readString("Beams:allowVertexSpread = on")
    pythia.readString("Beams:sigmaVertexX = 0.02")
    pythia.readString("Beams:sigmaVertexY = 0.02")
    pythia.readString("Beams:sigmaVertexZ = 50.0")
    
    # Allow longer-lived hadrons to decay with displaced vertices (units: mm)
    pythia.readString("ParticleDecays:limitTau0 = on")
    pythia.readString("ParticleDecays:tau0Max = 1e6")
    
    if not pythia.init():
        raise RuntimeError("pythia.init() failed")
    
    accepted = 0
    tried = 0
    
    MM_TO_M = 1e-3
    
    result: dict[str, Any] = {
        "meta": {
            "n_events": int(n_events),
            "sqrt_s_gev": float(ecm_gev),
            "process": str(process),
            "pthat_min_gev": float(pthat_min_gev),
            "seed": int(seed),
        },
        "events": [],
    }
    
    while accepted < n_events:
        tried += 1
        if not pythia.next():
            continue
        
        info = pythia.infoPython()
        # print(
        #     f"Process: {info.name()}  code={info.code()}  pTHat={info.pTHat():.2f}  "
        #     f"nMPI={info.nMPI()} nISR={info.nISR()} nFSR={info.nFSRinProc()}")
        # print_tree(pythia.event, 1, max_depth=25, show_kin=False, show_vtx=False,
        #            only_if=lambda p: p.status() not in [83, 84, -83, -84, 91, -91])
        # print_tree(pythia.event, 2, max_depth=25, show_kin=False, show_vtx=False,
        #            only_if=lambda p: p.status() not in [83, 84, -83, -84, 91, -91])
        
        event_desc = summarize_event(pythia)
        # print(event_desc)
        
        # Build one event (charged tracks only, like your current display expects)
        particles = []
        for p in pythia.event:
            debug_prints = False
            
            if p.status() < 0:
                if debug_prints:
                    print(f"Skipping particle with status {p.status()}, id {p.id()}, "
                          f"name {PID_LABEL.get(p.id(), str(p.id()))}")
                continue
            
            q = int(p.charge())
            # if q == 0:
            #     continue
            
            if is_neutrino(p.id()):
                if not keep_neutrinos:
                    if debug_prints:
                        print(f"Skipping neutrino id {p.id()}")
                    continue
            
            if debug_prints:
                print(f" Keeping particle status {p.status()}, id {p.id()}, "
                      f"name {PID_LABEL.get(p.id(), str(p.id()))}, ")
                
            particles.append(
                {
                    "id": int(p.id()),
                    "q": q,
                    "px": float(p.px()),
                    "py": float(p.py()),
                    "pz": float(p.pz()),
                    "e": float(p.e()),
                    "x0": float(p.xProd()) * MM_TO_M,
                    "y0": float(p.yProd()) * MM_TO_M,
                    "z0": float(p.zProd()) * MM_TO_M,
                    
                }
            )
        
        accepted += 1
        result["events"].append(
            {
                "event": accepted,
                "pTHat": float(pythia.infoPython().pTHat()),
                "particles": particles,
                "event_desc": event_desc,
            }
        )
        
        if accepted % 100 == 0 or accepted == 1:
            print(
                f"accepted={accepted}/{n_events} tried={tried} "
                f"pTHat={pythia.infoPython().pTHat():.2f} GeV"
            )
    
    # (Optional) print stats; you can also store in result["meta"] if desired
    # pythia.stat()
    try:
        result["meta"]["sigmaGen_mb"] = float(pythia.info.sigmaGen())
        result["meta"]["sigmaErr_mb"] = float(pythia.info.sigmaErr())
    except Exception:
        pass
    
    return result


def unit(vx, vy):
    n = math.hypot(vx, vy)
    if n == 0:
        return 0.0, 0.0
    return vx / n, vy / n


def render_event_3d_spin(
    event: dict[str, Any],
    *,
    B_T: float = 3.8,
    R_det_m: float = 1.2,
    Z_det_m: float = 3.0,
    pt_min_gev: float = 1.0,
    max_tracks: int = 250,
    n_steps_track: int = 260,
    s_max_m: float = 10.0,
    fps: int = 30,
    spin_seconds: float = 10.0,
    elev: float = 18.0,
    dpi: int = 140,
    bitrate: int = 1800,  # tune up/down
    filetype: str = "mp4",
    figsize: tuple[int, int] = (5, 5),
    p1: str = "2212",
    p2: str = "2212",
    energy_tev: float = 13.0,
) -> io.BytesIO:
    particles = event["particles"]

    def pt_of(p: dict[str, Any]) -> float:
        return math.hypot(float(p["px"]), float(p["py"]))

    particles = sorted(particles, key=pt_of, reverse=True)

    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = fig.add_subplot(111, projection="3d")
    p1_name = PID_LABEL.get(int(p1), p1)
    p2_name = PID_LABEL.get(int(p2), p2)
    fig.text(
        0.98, 0.98,
        f"{p1_name}-{p2_name} Collision at {energy_tev:.1f} TeV (B={B_T} T)",
        ha="right", va="top",
        fontsize=10,
        bbox=dict(facecolor="white", alpha=0.8, edgecolor="none", pad=2),
    )
    # Remove outer padding
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    
    # Force the 3D axes to fill the canvas
    ax.set_position((0.0, 0.0, 1.0, 1.0))
    
    ax.set_xlabel("x [m]")
    ax.set_ylabel("y [m]")
    ax.set_zlabel("z [m]")

    # Detector wireframe cylinder
    theta = np.linspace(0, 2 * np.pi, 80)
    z = np.linspace(-Z_det_m, Z_det_m, 2)
    Theta, Z = np.meshgrid(theta, z)
    Xc = R_det_m * np.cos(Theta)
    Yc = R_det_m * np.sin(Theta)
    ax.plot_wireframe(Xc, Yc, Z, linewidth=0.3)

    for zcap in (-Z_det_m, Z_det_m):
        ax.plot(
            R_det_m * np.cos(theta),
            R_det_m * np.sin(theta),
            zcap * np.ones_like(theta),
            linewidth=0.5,
        )

    def lw_from_pt(pt: float) -> float:
        return 0.6 + 0.8 * math.log10(max(pt, 0.1))

    plotted = 0
    particle_count: dict[int, int] = {}
    debug_prints = False
    for p in particles:
        if plotted >= max_tracks:
            break

        q_raw = int(p.get("q", 0))
        # if q_raw == 0:
        #     continue

        x0, y0, z0 = float(p["x0"]), float(p["y0"]), float(p["z0"])
        px, py, pz = float(p["px"]), float(p["py"]), float(p["pz"])
        pt = math.hypot(px, py)
        if pt < pt_min_gev:
            if debug_prints:
                print(f" Skipping track with pT={pt:.2f} GeV < pt_min_gev={pt_min_gev:.2f} GeV, "
                      f"id={p.get('id',0)}, name={PID_LABEL.get(int(p.get('id',0)), str(p.get('id',0)))}")
            continue
        else:
            if debug_prints:
                print(f" Plotting track with pT={pt:.2f} GeV >= pt_min_gev={pt_min_gev:.2f} GeV, "
                      f"id={p.get('id',0)}, name={PID_LABEL.get(int(p.get('id',0)), str(p.get('id',0)))}")
            
        if q_raw != 0:
            pts = _helix_points_from_momentum(
                x0=x0, y0=y0, z0=z0,
                px=px, py=py, pz=pz,
                q_raw=q_raw,
                B_T=B_T,
                R_det_m=R_det_m,
                Z_det_m=Z_det_m,
                n_steps=n_steps_track,
                s_max=s_max_m,
            )
        else:
            pts = _ray_points_from_momentum(
                x0=x0, y0=y0, z0=z0,
                px=px, py=py, pz=pz,
                R_det_m=R_det_m,
                Z_det_m=Z_det_m,
                n_steps=n_steps_track,
            )
        if pts is None:
            continue

        x, y, zz = pts
        # use solid line for most particles except neutrinos, use dashed lines for neutrinos
        if is_neutrino(p['id']):
            linestyle = "dashed"
            alpha = 0.65
        else:
            linestyle = "solid"
            alpha = 0.95
        
        ax.plot(
            x, y, zz,
            linewidth=lw_from_pt(pt),
            color=color_for_pid(p['id']),
            alpha=alpha,
            linestyle=linestyle,
        )
        plotted += 1
        pid = int(p.get("id", 0))
        particle_count[pid] = particle_count.get(pid, 0) + 1
    
    # Add a text box showing particle counts
    # --- draw a textbox background (single patch) ---
    x0, y0 = 0.02, 0.98
    line_h = 0.028  # figure fraction; tune based on fontsize/dpi
    lines = make_counts_lines(particle_count)
    
    # optional: background box using a transparent text as an anchor
    bg_text = "\n".join([t for t, _ in lines])
    bg = fig.text(
        x0, y0, bg_text,
        ha="left", va="top",
        fontsize=9,
        family="monospace",
        color=(0, 0, 0, 0),  # fully transparent text, just to size the bbox
        bbox=dict(boxstyle="round,pad=0.35", facecolor="white", alpha=0.8, edgecolor="none"),
    )
    
    # then place colored lines on top
    for i, (txt, col) in enumerate(lines):
        fig.text(
            x0, y0 - i * line_h, txt,
            ha="left", va="top",
            fontsize=9,
            family="monospace",
            color=col,
        )

    # Incoming proton beams (stylized)
    ax.plot([0.0, 0.0], [0.0, 0.0], [Z_det_m, 0.0], linewidth=2.0, alpha=0.9, color="tab:blue")
    ax.plot([0.0, 0.0], [0.0, 0.0], [-Z_det_m, 0.0], linewidth=2.0, alpha=0.9, color="tab:blue")
    ax.quiver(0, 0,  0.6 * Z_det_m, 0, 0, -1, length=0.35 * Z_det_m, normalize=True, linewidth=2.0, color="tab:blue")
    ax.quiver(0, 0, -0.6 * Z_det_m, 0, 0,  1, length=0.35 * Z_det_m, normalize=True, linewidth=2.0, color="tab:blue")

    ax.set_box_aspect((1, 1, 1))
    ax.set_xlim(-R_det_m, R_det_m)
    ax.set_ylim(-R_det_m, R_det_m)
    ax.set_zlim(-Z_det_m, Z_det_m)

    # Animation: spin camera
    n_frames = max(1, int(fps * spin_seconds))
    
    def update(i: int):
        az = 360.0 * (i / n_frames)
        ax.view_init(elev=elev, azim=az)
        return (ax,)

    ani = FuncAnimation(fig, update, frames=n_frames, interval=1000 / fps, blit=False, repeat=True)

    # Save to temp gif / mp4 using ffmpeg, then read into memory
    if filetype == "mp4":
        writer = FFMpegWriter(
            fps=fps,
            bitrate=bitrate,
            codec="libx264",
            extra_args=["-pix_fmt", "yuv420p"],  # best compatibility for Discord/mobile
        )
    elif filetype == "gif":
        writer = PillowWriter(fps=fps)
    else:
        raise ValueError(f"Unsupported filetype: {filetype}")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{filetype}", delete=False) as tmp:
            tmp_path = tmp.name
        
        t1 = perf_counter()
        ani.save(tmp_path, writer=writer)
        t2 = perf_counter()
        print(f"Saved animation to {tmp_path} in {t2 - t1:.2f} seconds")
        
        with open(tmp_path, "rb") as f:
            data = f.read()

        buf = io.BytesIO(data)
        buf.seek(0)
        return buf

    finally:
        plt.close(fig)
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


if __name__ == "__main__":
    p1 = "2212"
    p2 = "2212"
    e_tev = 13.0
    run_events(
        n_events=1,
        ecm_gev=e_tev * 1000.0,
        p1=p1, p2=p2,
        process=["HardQCD:all = on",
                 "WeakSingleBoson:all = on",
                 "PromptPhoton:all = on",
                 "WeakBosonExchange:all = on",
                 ],
        pthat_min_gev=30.0,
        seed=795170135,
    )

else:
    import discord
    from discord.ext import commands
    from cogs.utils.BotUtils import bot_utils as utils

    class ColliderCog(commands.Cog):
        def __init__(self, bot: commands.Bot):
            self.bot = bot
    
        @commands.command()
        @commands.cooldown(rate=1, per=15.0, type=commands.BucketType.user)
        async def collider(self, ctx: commands.Context, p1: str = "p", p2: str = "p",
                           e_tev: float = 13.0):
            """
            Simulate and render a collider event between two particles.
            Usage: `;collider [p1] [p2] [e_tev]`
            Example: `;collider p p 13.0`
    
            Can collide: p, pbar, pi+, pi-, K+, K-, e+, e-, mu+, mu-,
            gamma, nu_e, nu_ebar, nu_mu, nu_mubar, nu_tau, nu_taubar
            """
            m = await ctx.send(f"Simulating {p1}-{p2} collision at {e_tev:.1f} TeV...\n"
                               f"-# Processing may take up to a minute. Please wait...")
            p1 = str(NAME_TO_PID.get(p1.lower(), p1))
            p2 = str(NAME_TO_PID.get(p2.lower(), p2))
            sim_task = utils.asyncio_task(run_events,
                n_events=1,
                ecm_gev=e_tev * 1000.0,
                p1=p1, p2=p2,
                process=["HardQCD:all = on",
                         "WeakSingleBoson:all = on",
                         "PromptPhoton:all = on",
                         "WeakBosonExchange:all = on",
                         ],
                pthat_min_gev=30.0,
                seed=0,
            )
            sim = await sim_task
    
            event0 = sim["events"][0]
            filetype = 'mp4'
            
            low_res = True
            if low_res:
                fps = 8
                spin_seconds = 8
                bitrate = 800
                dpi = 80
                figsize = (4, 4)
            else:
                fps = 12
                spin_seconds = 16
                bitrate = 1400
                dpi = 120
                figsize = (5, 5)
                
            buf_task = utils.asyncio_task(render_event_3d_spin,
                                              event0,
                                              p1=p1, p2=p2,
                                              energy_tev=13.0,
                                              B_T=7,
                                              R_det_m=1.2,
                                              Z_det_m=3.0,
                                              pt_min_gev=1.0,
                                              max_tracks=2000,
                                              fps=fps,
                                              spin_seconds=spin_seconds,
                                              bitrate=bitrate,
                                              dpi=dpi,
                                              filetype=filetype,
                                              figsize=figsize,
                                              )
            buf = await buf_task
    
            file = discord.File(fp=buf, filename=f"collider.{filetype}")
            await m.edit(content=event0["event_desc"], attachments=[file])
            
    async def setup(bot: commands.Bot):
        await bot.add_cog(ColliderCog(bot))
