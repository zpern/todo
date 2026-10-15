from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


DEFAULT_GMSH = Path(r"C:\Users\zpern\Downloads\gmsh-4.15.2-Windows64\gmsh-4.15.2-Windows64\gmsh.exe")
RECOMBINE_MODES = ("balanced", "quality", "preserve")


def nums(line: str) -> list[str]:
    return re.findall(r"[-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?", line)


def read_pls(path: Path):
    lines = path.read_text(errors="ignore").splitlines()
    if not lines:
        raise ValueError("empty file")
    header = [int(float(x)) for x in nums(lines[0])]
    if len(header) < 2:
        raise ValueError("bad .pls header")
    n_tri, n_node = header[0], header[1]
    if len(lines) < 1 + n_node + n_tri:
        raise ValueError(f".pls too short for n_tri={n_tri}, n_node={n_node}")

    points: list[tuple[float, float, float]] = []
    for line in lines[1 : 1 + n_node]:
        p = nums(line)
        if len(p) < 4:
            raise ValueError(f"bad node line: {line!r}")
        points.append((float(p[1]), float(p[2]), float(p[3])))

    tris: list[tuple[int, int, int, int]] = []
    for line in lines[1 + n_node : 1 + n_node + n_tri]:
        p = nums(line)
        if len(p) < 4:
            raise ValueError(f"bad triangle line: {line!r}")
        patch = int(float(p[4])) if len(p) >= 5 else 1
        tris.append((int(float(p[1])), int(float(p[2])), int(float(p[3])), patch))
    return points, tris


def write_tri_msh(path: Path, points, tris) -> None:
    patches = sorted({t[3] for t in tris}) or [1]
    with path.open("w", newline="\n") as f:
        f.write("$MeshFormat\n2.2 0 8\n$EndMeshFormat\n")
        f.write("$PhysicalNames\n")
        f.write(f"{len(patches)}\n")
        for p in patches:
            f.write(f'2 {p} "patch_{p}"\n')
        f.write("$EndPhysicalNames\n")
        f.write("$Nodes\n")
        f.write(f"{len(points)}\n")
        for i, (x, y, z) in enumerate(points, 1):
            f.write(f"{i} {x:.17g} {y:.17g} {z:.17g}\n")
        f.write("$EndNodes\n")
        f.write("$Elements\n")
        f.write(f"{len(tris)}\n")
        for i, (a, b, c, patch) in enumerate(tris, 1):
            f.write(f"{i} 2 2 {patch} {patch} {a} {b} {c}\n")
        f.write("$EndElements\n")


def read_msh2_surface(path: Path):
    lines = path.read_text(errors="ignore").splitlines()
    ni = lines.index("$Nodes")
    ei = lines.index("$Elements")
    n_nodes = int(lines[ni + 1])
    nodes: dict[int, tuple[float, float, float]] = {}
    for line in lines[ni + 2 : ni + 2 + n_nodes]:
        p = line.split()
        nodes[int(p[0])] = (float(p[1]), float(p[2]), float(p[3]))

    n_elements = int(lines[ei + 1])
    faces: list[tuple[int, ...]] = []
    patches: list[int] = []
    for line in lines[ei + 2 : ei + 2 + n_elements]:
        p = line.split()
        if len(p) < 4:
            continue
        etype = int(p[1])
        ntags = int(p[2])
        patch = int(p[3]) if ntags >= 1 else 1
        conn = tuple(int(x) for x in p[3 + ntags :])
        if etype == 2 and len(conn) == 3:
            faces.append(conn)
            patches.append(patch)
        elif etype == 3 and len(conn) == 4:
            faces.append(conn)
            patches.append(patch)

    used = sorted({nid for face in faces for nid in face})
    renum = {nid: i for i, nid in enumerate(used)}
    points = [nodes[nid] for nid in used]
    zero_faces = [tuple(renum[nid] for nid in face) for face in faces]
    return points, zero_faces, patches


def count_faces(faces) -> tuple[int, int]:
    tris = sum(1 for f in faces if len(f) == 3)
    quads = sum(1 for f in faces if len(f) == 4)
    return tris, quads


def write_ply(path: Path, points, faces) -> None:
    with path.open("w", newline="\n") as f:
        f.write("ply\nformat ascii 1.0\n")
        f.write("comment Gmsh RecombineMesh result from .pls triangle surface mesh\n")
        f.write(f"element vertex {len(points)}\n")
        f.write("property float x\nproperty float y\nproperty float z\n")
        f.write(f"element face {len(faces)}\n")
        f.write("property list uchar int vertex_indices\n")
        f.write("end_header\n")
        for x, y, z in points:
            f.write(f"{x:.17g} {y:.17g} {z:.17g}\n")
        for face in faces:
            f.write(str(len(face)) + " " + " ".join(str(i) for i in face) + "\n")


def write_fluent_msh(path: Path, points, faces, patches) -> None:
    n_nodes = len(points)
    n_faces = len(faces)

    with path.open("w", newline="\n") as f:
        f.write('(0 "Fluent ASCII surface mesh exported from Gmsh RecombineMesh result")\n')
        f.write('(0 "Boundary face zones are split by .pls patch id: zone id = patch id + 1")\n')
        f.write("(2 3)\n\n")

        f.write(f"(10 (0 1 {n_nodes:x} 0 3))\n")
        f.write(f"(10 (1 1 {n_nodes:x} 1 3)(\n")
        for x, y, z in points:
            f.write(f"{x:.17g} {y:.17g} {z:.17g}\n")
        f.write("))\n\n")

        f.write(f"(13 (0 1 {n_faces:x} 0 0))\n")
        next_face_id = 1
        for patch in sorted(set(patches)):
            zone_id = patch + 1
            for face_size, face_type in ((3, 3), (4, 4)):
                zone_faces = [face for face, p in zip(faces, patches) if p == patch and len(face) == face_size]
                if not zone_faces:
                    continue
                first = next_face_id
                last = first + len(zone_faces) - 1
                f.write(f'(0 "patch_{patch}: zone {zone_id}, {len(zone_faces)} face(s), type {face_type}")\n')
                f.write(f"(13 ({zone_id:x} {first:x} {last:x} 3 {face_type})(\n")
                for face in zone_faces:
                    node_ids = [i + 1 for i in face]
                    if face_size == 3:
                        f.write(f"{node_ids[0]:x} {node_ids[1]:x} {node_ids[2]:x} 0 0\n")
                    else:
                        f.write(f"{node_ids[0]:x} {node_ids[1]:x} {node_ids[2]:x} {node_ids[3]:x} 0 0\n")
                f.write("))\n")
                next_face_id = last + 1


def gmsh_recombine_options(mode: str) -> list[str]:
    if mode == "quality":
        return [
            "Mesh.RecombinationAlgorithm = 3;",
            "Mesh.RecombineOptimizeTopology = 10;",
            "Mesh.RecombineNodeRepositioning = 1;",
            "Mesh.Smoothing = 10;",
        ]
    if mode == "preserve":
        return [
            "Mesh.RecombinationAlgorithm = 1;",
            "Mesh.RecombineOptimizeTopology = 0;",
            "Mesh.RecombineNodeRepositioning = 0;",
            "Mesh.Smoothing = 0;",
        ]
    if mode == "balanced":
        return [
            "Mesh.RecombinationAlgorithm = 2;",
            "Mesh.RecombineOptimizeTopology = 5;",
            "Mesh.RecombineNodeRepositioning = 1;",
            "Mesh.Smoothing = 2;",
        ]
    raise ValueError(f"unknown recombine mode: {mode}")


def process(pls: Path, gmsh: Path, timeout: float, keep_intermediate: bool, mode: str):
    points, tris = read_pls(pls)
    case_dir = pls.parent
    stem = pls.stem
    tmp = case_dir / "_gmsh_recombine_tmp"
    tmp.mkdir(exist_ok=True)
    tri_msh = tmp / f"{stem}_tri.msh"
    geo = case_dir / f"{stem}_gmsh_recombine_{mode}.geo"
    out_msh = case_dir / f"{stem}_gmsh_recombine_{mode}.msh"
    out_ply = case_dir / f"{stem}_gmsh_recombine_{mode}.ply"
    out_fluent_msh = case_dir / f"{stem}_gmsh_recombine_{mode}_fluent.msh"

    for old_output in (out_msh, out_ply, out_fluent_msh):
        try:
            old_output.unlink()
        except FileNotFoundError:
            pass

    write_tri_msh(tri_msh, points, tris)
    geo.write_text(
        '\n'.join(
            [
                f'Merge "_gmsh_recombine_tmp/{stem}_tri.msh";',
                "Mesh.RecombineAll = 1;",
                *gmsh_recombine_options(mode),
                "RecombineMesh;",
                f'Save "{stem}_gmsh_recombine_{mode}.msh";',
                "",
            ]
        )
    )

    try:
        proc = subprocess.run(
            [str(gmsh), geo.name, "-parse_and_exit", "-format", "msh2", "-o", out_msh.name],
            cwd=case_dir,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
        ret: object = proc.returncode
        tail = "\n".join(proc.stdout.splitlines()[-8:])
    except subprocess.TimeoutExpired:
        ret = "timeout"
        tail = "timeout"

    if ret != 0:
        raise RuntimeError(f"Gmsh failed, return={ret}, tail={tail}")
    if not out_msh.exists():
        raise RuntimeError(f"Gmsh did not create output, return={ret}, tail={tail}")

    out_points, faces, patches = read_msh2_surface(out_msh)
    out_tris, out_quads = count_faces(faces)
    write_ply(out_ply, out_points, faces)
    write_fluent_msh(out_fluent_msh, out_points, faces, patches)

    if not keep_intermediate:
        for p in (tri_msh, geo):
            try:
                p.unlink()
            except OSError:
                pass
        try:
            tmp.rmdir()
        except OSError:
            pass

    return {
        "input_points": len(points),
        "input_triangles": len(tris),
        "output_points": len(out_points),
        "output_faces": len(faces),
        "output_triangles": out_tris,
        "output_quads": out_quads,
        "output_patches": len(set(patches)),
        "output_msh": out_msh,
        "output_ply": out_ply,
        "output_fluent_msh": out_fluent_msh,
        "mode": mode,
        "gmsh_return": ret,
        "gmsh_tail": tail.replace("\t", " ").replace("\n", " | "),
    }


def find_pls_files(root: Path, model: str | None) -> list[Path]:
    if not model:
        return sorted(root.rglob("*.pls"))

    candidate = Path(model)
    if candidate.suffix.lower() == ".pls":
        path = candidate if candidate.is_absolute() else root / candidate
        if not path.exists():
            raise FileNotFoundError(f"model .pls not found: {path}")
        return [path]

    path = candidate if candidate.is_absolute() else root / candidate
    if path.is_dir():
        files = sorted(path.rglob("*.pls"))
        if not files:
            raise FileNotFoundError(f"no .pls found under model directory: {path}")
        return files

    matches = sorted(root.rglob(f"{model}.pls"))
    if not matches:
        matches = sorted(p for p in root.rglob("*.pls") if model in p.stem or model in p.parent.name)
    if not matches:
        raise FileNotFoundError(f"no .pls matched model: {model}")
    return matches


def main() -> int:
    ap = argparse.ArgumentParser(description="Batch run Gmsh RecombineMesh on .pls triangle surface meshes and export PLY plus Fluent surface mesh.")
    ap.add_argument("--root", type=Path, default=Path("test_case"))
    ap.add_argument("--model", help="Run only one model by name, directory, or .pls path. Omit to run all .pls files.")
    ap.add_argument("--gmsh", type=Path, default=DEFAULT_GMSH)
    ap.add_argument("--timeout", type=float, default=300.0)
    ap.add_argument("--keep-intermediate", action="store_true")
    ap.add_argument(
        "--mode",
        choices=RECOMBINE_MODES,
        default="balanced",
        help=(
            "Gmsh recombination strategy. "
            "quality allows more optimization/smoothing; "
            "preserve keeps the input surface closer by disabling node repositioning; "
            "balanced is the default middle ground."
        ),
    )
    args = ap.parse_args()

    rows = []
    pls_files = find_pls_files(args.root, args.model)
    print(f"SELECTED {len(pls_files)} .pls file(s)", flush=True)
    for pls in pls_files:
        try:
            r = process(pls, args.gmsh, args.timeout, args.keep_intermediate, args.mode)
            rows.append((True, pls, r, ""))
            print(
                f"OK\t{pls}\tmode={r['mode']}\tpatches={r['output_patches']}\tquads={r['output_quads']}\ttriangles={r['output_triangles']}\tfluent_msh={r['output_fluent_msh']}",
                flush=True,
            )
        except Exception as e:
            rows.append((False, pls, {}, repr(e)))
            print(f"FAIL\t{pls}\t{e!r}", flush=True)

    report = args.root / f"gmsh_recombine_{args.mode}_report.tsv"
    with report.open("w", newline="\n") as f:
        f.write("ok\tmode\tinput\toutput_gmsh_msh\toutput_ply\toutput_fluent_msh\tinput_points\tinput_triangles\toutput_points\toutput_faces\toutput_triangles\toutput_quads\toutput_patches\tgmsh_return\terror_or_tail\n")
        for ok, inp, r, err in rows:
            f.write(
                f"{ok}\t{r.get('mode', args.mode)}\t{inp}\t{r.get('output_msh','')}\t{r.get('output_ply','')}\t{r.get('output_fluent_msh','')}\t{r.get('input_points',0)}\t{r.get('input_triangles',0)}\t{r.get('output_points',0)}\t{r.get('output_faces',0)}\t{r.get('output_triangles',0)}\t{r.get('output_quads',0)}\t{r.get('output_patches',0)}\t{r.get('gmsh_return','')}\t{err or r.get('gmsh_tail','')}\n"
            )
    print(f"SUMMARY total={len(rows)} ok={sum(1 for r in rows if r[0])} failed={sum(1 for r in rows if not r[0])}", flush=True)
    print(f"REPORT {report}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
