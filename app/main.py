from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from flask import Flask, Response, render_template, request, redirect, url_for, flash, send_from_directory

from instance_generator import (
    InstanceParams,
    generate_instance,
    instance_to_string,
    min_round_trip_over_mandatories,
    sum_mandatory_time,
)
from instance_models import C_MIN, C_MAX, N_MIN, N_MAX, M_MIN, M_MAX, T_MIN, T_MAX, Street
from instance_validator import validate_generated_instance, parse_instance_file, check_full_feasibility_greedy


BASE_DIR = Path(__file__).resolve().parents[1]
INSTANCES_DIR = BASE_DIR / "instances"
INSTANCES_8H_DIR = INSTANCES_DIR / "8h_strict"
T_8H = 28800
MAX_ATTEMPTS_8H = 500


def _sample_size_label(n_junctions: int, n_streets: int) -> str:
    """UI label for bundled samples: large vs medium from graph size."""
    if n_junctions >= 100 or n_streets >= 400:
        return "large"
    return "medium"


def create_app() -> Flask:
    app = Flask(__name__)
    # This is only used for flash messages; in production you should override it.
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key")

    @app.route("/", methods=["GET"])
    def index():
        """
        Show the main page with:
        - Instance generation form
        - Instance validation form
        """
        # Simple defaults that mirror the CLI in instance_generator.main
        default_params = {
            "n_junctions": 20,
            "n_streets": 45,
            "time_limit": 3600,
            "n_vehicles": 3,
            "depot": 0,
            "alpha": 0.5,
            "seed": "",
            "filename": "instance.txt",
        }

        # Predefined example instances to show under the generator
        sample_names = [
            "instance_A.txt",
            "instance_B.txt",
            "instance_C.txt",
            "instance_D.txt",
            "instance_E.txt",
        ]
        samples: list[dict] = []
        for name in sample_names:
            path = INSTANCES_DIR / name
            if not path.is_file():
                continue
            try:
                params, _streets, vehicle_types = parse_instance_file(str(path))
            except Exception:
                continue
            samples.append(
                {
                    "name": name,
                    "n_junctions": params.n_junctions,
                    "n_streets": params.n_streets,
                    "time_limit": params.time_limit,
                    "n_vehicles": params.n_vehicles,
                    "depot": params.depot,
                    "alpha": getattr(params, "alpha", 0.5),
                    "vehicle_types": " ".join(vehicle_types),
                    "size_label": _sample_size_label(
                        params.n_junctions, params.n_streets
                    ),
                }
            )

        # Predefined 8h fixed instances (instances/8h_strict/*.txt)
        samples_8h: list[dict] = []
        if INSTANCES_8H_DIR.is_dir():
            for path in sorted(INSTANCES_8H_DIR.glob("*.txt")):
                name = path.name
                try:
                    params, _streets, vehicle_types = parse_instance_file(str(path))
                except Exception:
                    continue
                samples_8h.append(
                    {
                        "name": name,
                        "n_junctions": params.n_junctions,
                        "n_streets": params.n_streets,
                        "time_limit": params.time_limit,
                        "n_vehicles": params.n_vehicles,
                        "depot": params.depot,
                        "alpha": getattr(params, "alpha", 0.5),
                        "vehicle_types": " ".join(vehicle_types),
                        "size_label": _sample_size_label(
                            params.n_junctions, params.n_streets
                        ),
                    }
                )

        return render_template(
            "index.html",
            default_params=default_params,
            instances_dir=str(INSTANCES_DIR.relative_to(BASE_DIR)),
            samples=samples,
            samples_8h=samples_8h,
        )

    @app.route("/generate", methods=["POST"])
    def generate():
        """
        Handle instance generation from form parameters.
        """
        try:
            n_junctions = int(request.form.get("n_junctions", 20))
            n_streets = int(request.form.get("n_streets", 45))
            time_limit = int(request.form.get("time_limit", 3600))
            n_vehicles = int(request.form.get("n_vehicles", 3))
            depot = int(request.form.get("depot", 0))
            alpha = float(request.form.get("alpha", 0.5))
            seed_raw = request.form.get("seed") or ""
            seed = int(seed_raw) if seed_raw.strip() else None
            filename = (request.form.get("filename") or "instance.txt").strip() or "instance.txt"
        except ValueError as e:
            flash(f"Invalid input: {e}", "error")
            return redirect(url_for("index"))

        # Basic bounds guardrails (use same constants as validator)
        if not (N_MIN <= n_junctions <= N_MAX):
            flash(f"n_junctions must be in [{N_MIN}, {N_MAX}]", "error")
            return redirect(url_for("index"))
        if not (M_MIN <= n_streets <= M_MAX):
            flash(f"n_streets must be in [{M_MIN}, {M_MAX}]", "error")
            return redirect(url_for("index"))
        if not (T_MIN <= time_limit <= T_MAX):
            flash(f"time_limit must be in [{T_MIN}, {T_MAX}]", "error")
            return redirect(url_for("index"))
        if not (C_MIN <= n_vehicles <= C_MAX):
            flash(f"n_vehicles must be in [{C_MIN}, {C_MAX}]", "error")
            return redirect(url_for("index"))
        if depot < 0 or depot >= n_junctions:
            flash("depot must be in [0, n_junctions-1]", "error")
            return redirect(url_for("index"))
        if not (0 <= alpha <= 1):
            flash("α must be in [0, 1]", "error")
            return redirect(url_for("index"))

        params = InstanceParams(
            n_junctions=n_junctions,
            n_streets=n_streets,
            time_limit=time_limit,
            n_vehicles=n_vehicles,
            depot=depot,
            alpha=alpha,
            seed=seed,
        )

        # Generate streets and vehicles, then adjust time_limit like CLI main.
        streets, vehicles = generate_instance(params)
        required_t = min_round_trip_over_mandatories(params.n_junctions, params.depot, streets)
        total_mandatory = sum_mandatory_time(streets)
        SLACK_MIN_SEC = 300
        SLACK_FRACTION = 0.5

        t_from_round_trip = 0
        if required_t != float("inf"):
            slack = max(SLACK_MIN_SEC, int(required_t * SLACK_FRACTION))
            t_from_round_trip = int(required_t) + slack

        t_from_budget = 0
        if params.n_vehicles > 0 and total_mandatory > 0:
            min_t_per_vehicle = (total_mandatory + params.n_vehicles - 1) // params.n_vehicles
            t_from_budget = min_t_per_vehicle + max(SLACK_MIN_SEC, min_t_per_vehicle // 2)

        params.time_limit = max(
            params.time_limit,
            t_from_round_trip,
            t_from_budget,
        )

        # Safe download filename (no path components)
        if "/" in filename or "\\" in filename or "\0" in filename:
            filename = "instance.txt"
        if not filename.endswith(".txt"):
            filename = filename.rstrip() + ".txt"

        content = instance_to_string(params, streets, vehicles)
        return Response(
            content,
            mimetype="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )

    @app.route("/validate", methods=["POST"])
    def validate():
        """
        Validate an uploaded instance file and show per-check results.
        """
        uploaded = request.files.get("instance_file")
        if not uploaded or uploaded.filename == "":
            flash("Please choose an instance file to upload.", "error")
            return redirect(url_for("index"))

        messages: List[dict] = []

        def report(msg: str) -> None:
            messages.append({"ok": True, "message": msg})

        try:
            raw = uploaded.stream.read().decode("utf-8")
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            if len(lines) < 2:
                raise ValueError(f"File has too few lines: {len(lines)}")
            parts = lines[0].split()
            if len(parts) != 6:
                raise ValueError(f"First line must have 6 values (N M T C S α), got {len(parts)}")
            n = int(parts[0])
            m = int(parts[1])
            T = int(parts[2])
            C = int(parts[3])
            depot = int(parts[4])
            alpha = float(parts[5])
            params = InstanceParams(
                n_junctions=n,
                n_streets=m,
                time_limit=T,
                n_vehicles=C,
                depot=depot,
                alpha=alpha,
                seed=None,
            )
            if len(lines) != 1 + m + 1:
                raise ValueError(f"Expected 1 + {m} + 1 = {1 + m + 1} lines, got {len(lines)}")
            streets: list[Street] = []
            for j in range(1, 1 + m):
                p = lines[j].split()
                if len(p) != 7:
                    raise ValueError(f"Street line {j}: expected 7 values, got {len(p)}")
                streets.append(
                    Street(
                        a=int(p[0]),
                        b=int(p[1]),
                        direction=int(p[2]),
                        traversal_time=int(p[3]),
                        length=int(p[4]),
                        category=p[5],
                        requirement=int(p[6]),
                    )
                )
            vehicle_types = lines[1 + m].split()
            if len(vehicle_types) != C:
                raise ValueError(f"Vehicle line: expected {C} types, got {len(vehicle_types)}")

            validate_generated_instance(params, streets, vehicle_types, report=report)
            overall_status = "valid"
            error_message = None
        except ValueError as e:
            # First failure stops validation; mark it as failed.
            overall_status = "invalid"
            error_message = str(e)
            messages.append({"ok": False, "message": error_message})

        return render_template(
            "validation_result.html",
            instance_rel=uploaded.filename or "uploaded instance",
            overall_status=overall_status,
            messages=messages,
            error_message=error_message,
        )

    def _is_feasible_for_t(
        n_junctions: int, depot: int, streets: list, time_limit: int, n_vehicles: int
    ) -> bool:
        required_t = min_round_trip_over_mandatories(n_junctions, depot, streets)
        if required_t == float("inf") or required_t > time_limit:
            return False
        total_mandatory = sum_mandatory_time(streets)
        if total_mandatory > n_vehicles * time_limit:
            return False
        return True

    @app.route("/generate-8h", methods=["POST"])
    def generate_8h():
        """
        Generate a feasible instance with T fixed at 8h (28800 s) and FULL FEASIBILITY: yes.
        Bounded retries; returns file download or redirects with error.
        """
        try:
            n_junctions = int(request.form.get("n_junctions_8h", 20))
            n_streets = int(request.form.get("n_streets_8h", 45))
            n_vehicles = int(request.form.get("n_vehicles_8h", 5))
            depot = int(request.form.get("depot_8h", 0))
            alpha = float(request.form.get("alpha_8h", 0.5))
            max_attempts = int(request.form.get("max_attempts_8h", 300))
        except (ValueError, TypeError):
            flash("Invalid parameters for 8h instance.", "error")
            return redirect(url_for("index"))
        max_attempts = min(max(max_attempts, 1), MAX_ATTEMPTS_8H)
        if not (N_MIN <= n_junctions <= N_MAX):
            flash(f"N must be in [{N_MIN}, {N_MAX}]", "error")
            return redirect(url_for("index"))
        if not (M_MIN <= n_streets <= M_MAX):
            flash(f"M must be in [{M_MIN}, {M_MAX}]", "error")
            return redirect(url_for("index"))
        if not (C_MIN <= n_vehicles <= C_MAX):
            flash(f"C must be in [{C_MIN}, {C_MAX}]", "error")
            return redirect(url_for("index"))
        if depot < 0 or depot >= n_junctions:
            flash("Depot must be in [0, N-1]", "error")
            return redirect(url_for("index"))
        if not (0 <= alpha <= 1):
            flash("α must be in [0, 1]", "error")
            return redirect(url_for("index"))

        for attempt in range(max_attempts):
            seed = attempt
            params = InstanceParams(
                n_junctions=n_junctions,
                n_streets=n_streets,
                time_limit=T_8H,
                n_vehicles=n_vehicles,
                depot=depot,
                alpha=alpha,
                seed=seed,
            )
            try:
                streets, vehicles = generate_instance(params)
            except Exception:
                continue
            if not _is_feasible_for_t(n_junctions, depot, streets, T_8H, n_vehicles):
                continue
            if not check_full_feasibility_greedy(
                n_junctions, depot, T_8H, n_vehicles, streets
            ):
                continue
            params.time_limit = T_8H
            content = instance_to_string(params, streets, vehicles)
            filename = request.form.get("filename_8h", "instance_8h.txt").strip()
            if not filename or "/" in filename or "\\" in filename:
                filename = "instance_8h.txt"
            if not filename.endswith(".txt"):
                filename = filename.rstrip() + ".txt"
            return Response(
                content,
                mimetype="text/plain",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "X-Generation-Attempt": str(attempt + 1),
                },
            )

        error_msg = (
            f"No instance with FULL FEASIBILITY: yes found in {max_attempts} attempts. "
            "Try smaller N/M, more vehicles (C), or higher max attempts."
        )
        return Response(
            json.dumps({"error": error_msg}),
            status=400,
            mimetype="application/json",
        )

    @app.route("/download-8h/<name>", methods=["GET"])
    def download_8h(name: str):
        """Download a predefined 8h instance from instances/8h_strict/."""
        if ".." in name or "/" in name or "\\" in name or not name.endswith(".txt"):
            flash("Invalid filename.", "error")
            return redirect(url_for("index"))
        path = INSTANCES_8H_DIR / name
        if not path.is_file():
            flash("8h instance not found.", "error")
            return redirect(url_for("index"))
        return send_from_directory(
            INSTANCES_8H_DIR,
            name,
            as_attachment=True,
            download_name=name,
        )

    @app.route("/download-sample/<name>", methods=["GET"])
    def download_sample(name: str):
        """
        Download one of the predefined sample instances from the instances/ folder.
        """
        allowed = {
            "instance_A.txt",
            "instance_B.txt",
            "instance_C.txt",
            "instance_D.txt",
            "instance_E.txt",
        }
        if name not in allowed:
            flash("Unknown sample instance.", "error")
            return redirect(url_for("index"))
        return send_from_directory(
            INSTANCES_DIR,
            name,
            as_attachment=True,
            download_name=name,
        )

    return app


app = create_app()


if __name__ == "__main__":
    # For local use: `python -m app.main` or `python app/main.py`
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

