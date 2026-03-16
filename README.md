# CLIPP Instance Generator

Instance generator for the **CLIPP** problem. The problem definition is given [here](https://drive.google.com/file/d/1cpVz1BvfG_ItNjddxG_KMIG5tULpsbd7/view?usp=sharing).

You can generate and validate instances in the browser:
**https://clipp-insancegenerator.onrender.com**

![CLIPP UI](Screenshot%20from%202026-03-15%2023-37-16.png)

Generate: set parameters and download the instance file. Validate: upload a `.txt` instance and see which checks pass or fail.

## Main scripts

- **`instance_generator.py`** — Generates random feasible CLIPP instances (graph, streets, vehicle types) and writes them to a file. 

- **`instance_validator.py`** — Checks that an instance file is valid: parameter bounds, street lines, vehicle line, graph reachability, capacity, and time limits. Optionally reports a greedy full-feasibility check.

## Create instances locally

**Generate an instance (CLI):**
```bash
python instance_generator.py -n 20 -m 45 -t 3600 -c 3 -s 0 -w 1.0 -o instances/my_instance.txt
```
Use `python instance_generator.py --help` for all options (`-n` junctions, `-m` streets, `-t` time limit, `-c` vehicles, `-s` depot, `-w` penalty, `--seed` optional, `-o` output path).

**Validate an instance:**
```bash
python instance_validator.py instances/my_instance.txt
```

**Run the web UI locally:**
```bash
pip install -r requirements.txt
python -m app.main
```
Then open **http://localhost:5000**.

## How an instance is created

1. Build a random **spanning tree** on *N* junctions so the graph is connected.
2. Add more edges until there are exactly **M** streets (no duplicate edges between the same pair of junctions).
3. Assign each street: **direction** (one-way or two-way; spanning-tree edges are two-way so the depot reaches all junctions), **traversal time**, **length**, **category** (M/O/C), and **requirement** (10/20/30; 0 for connector). At least one street is mandatory (M).
4. Generate **C** vehicle types at random from {S, M, L}.
5. Compute the minimum time limit so that: (a) each mandatory street has depot→street→depot ≤ *T*, and (b) total mandatory traversal time ≤ *C*×*T*. Raise *T* with slack so instances are not too tight.

---

## Validation checks

1. **Parameter bounds** — *N*, *M*, *T*, *C*, depot, and *W* within problem bounds; *M* between *N*−1 and max edges.
2. **Streets** — Correct number of streets; each street has valid junctions, direction, time, length, category, requirement; no duplicate edge between the same two junctions.
3. **Vehicles** — Exactly *C* vehicle types, each in {S, M, L}.
4. **Graph** — Every junction is reachable from the depot following street directions.
5. **Capacity** — For every mandatory street, at least one vehicle has capacity ≥ the street’s requirement.
6. **Time limit** — Each mandatory street has depot→street→depot ≤ *T*; total mandatory time ≤ *C*×*T*.
7. **Full feasibility** (optional) — A greedy packing checks whether all mandatory streets can be assigned to *C* routes each within time *T* (heuristic; failure does not prove infeasibility).
