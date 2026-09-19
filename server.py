#!/usr/bin/env python3
"""
garmin-mcp — Garmin Connect data as MCP tools
==============================================
Exposes activities, sleep, resting heart rate, and body battery from
Garmin Connect (via the unofficial `garminconnect` library).

Auth: set GARMIN_EMAIL / GARMIN_PASSWORD env vars (see garmin_auth.py).

Transport: stdio (Claude Code / Claude Desktop MCP config)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date

from fastmcp import FastMCP

from garmin_auth import get_client
from garminconnect.workout import (
    ConditionType,
    ExecutableStep,
    RepeatGroup,
    RunningWorkout,
    StepType,
    SwimmingWorkout,
    TargetType,
    WorkoutSegment,
)

logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

mcp = FastMCP(
    name="garmin-mcp",
    instructions="""
Garmin Connect data tools. All date args are ISO format (YYYY-MM-DD);
omit them to default to today.

  get_activities            Recent workouts/activities
  get_resting_heart_rate    Resting + all-day heart rate data for a date
  get_sleep                 Sleep data for a date
  get_body_battery          Body battery levels for a date
  create_activity           Manually log a private activity (no GPS/sensor data)
  create_running_workout    Build a structured running workout (warmup/interval/
                             recovery/repeat/cooldown, with pace targets) and
                             push it to Garmin Connect so it syncs to the watch
  create_swimming_workout   Build a structured pool workout (warmup/interval/
                             recovery/repeat/cooldown, with per-100m pace
                             targets and stroke types) and push it to Garmin
                             Connect so it syncs to the watch
  list_workouts             List saved workout templates
  delete_workout            Delete a workout template from the workout library
  unschedule_workout        Remove a scheduled workout from the calendar
                             (keeps the template itself)
""",
)

def _today() -> str:
    return date.today().isoformat()


@mcp.tool
def get_activities(limit: int = 10) -> str:
    """
    Get recent Garmin activities/workouts.

    Args:
        limit: Max number of activities to return (default 10)
    """
    result = get_client().get_activities(0, limit)
    return json.dumps(result, indent=2)


@mcp.tool
def get_resting_heart_rate(cdate: str | None = None) -> str:
    """
    Get heart rate data (including resting HR) for a date.

    Args:
        cdate: Date in YYYY-MM-DD format. Defaults to today.
    """
    result = get_client().get_heart_rates(cdate or _today())
    return json.dumps(result, indent=2)


@mcp.tool
def get_sleep(cdate: str | None = None) -> str:
    """
    Get sleep data for a date.

    Args:
        cdate: Date in YYYY-MM-DD format. Defaults to today.
    """
    result = get_client().get_sleep_data(cdate or _today())
    return json.dumps(result, indent=2)


@mcp.tool
def get_body_battery(startdate: str | None = None, enddate: str | None = None) -> str:
    """
    Get body battery levels for a date range.

    Args:
        startdate: Start date in YYYY-MM-DD format. Defaults to today.
        enddate:   End date in YYYY-MM-DD format. Defaults to startdate.
    """
    result = get_client().get_body_battery(startdate or _today(), enddate)
    return json.dumps(result, indent=2)


@mcp.tool
def create_activity(
    activity_name: str,
    type_key: str,
    start_datetime: str,
    distance_km: float,
    duration_min: int,
    time_zone: str = "Asia/Jerusalem",
) -> str:
    """
    Manually log a private activity on Garmin Connect (no GPS/sensor data).

    Args:
        activity_name: Title of the activity, e.g. "Evening Run".
        type_key: Garmin activity type key, e.g. "running", "cycling", "hiking",
            "open_water_swimming", "strength_training". See the "activity_type_*"
            keys at https://connect.garmin.com/modern/main/js/properties/activity_types/activity_types.properties
            (use the key without the "activity_type_" prefix).
        start_datetime: Local start time, ISO format "YYYY-MM-DDTHH:MM:SS.000".
        distance_km: Distance in kilometers (use 0 for non-distance activities).
        duration_min: Duration in minutes.
        time_zone: IANA timezone of the activity. Defaults to Asia/Jerusalem.
    """
    result = get_client().create_manual_activity(
        start_datetime=start_datetime,
        time_zone=time_zone,
        type_key=type_key,
        distance_km=distance_km,
        duration_min=duration_min,
        activity_name=activity_name,
    )
    return json.dumps(result, indent=2)


def _pace_to_mps(pace_min_per_unit: str, pace_unit_m: float) -> float:
    """
    Convert a 'M:SS' pace string to meters/second (Garmin's unit).
    pace_unit_m is the distance the pace is quoted per: 1000 for running
    (per-km), 100 for swimming (per-100m).
    """
    minutes, seconds = pace_min_per_unit.split(":")
    sec_per_unit = int(minutes) * 60 + float(seconds)
    return pace_unit_m / sec_per_unit


def _pace_target(fast_pace: str, slow_pace: str, pace_unit_m: float) -> dict:
    """
    Build a PACE_ZONE target. Garmin stores targets as a speed range in m/s,
    so the *faster* pace (smaller min:sec) becomes the *larger* value.
    `targetValueOne`/`targetValueTwo` are siblings of `targetType` on the
    step itself in Garmin's schema, not nested inside it.
    """
    return {
        "targetType": {
            "workoutTargetTypeId": TargetType.PACE_ZONE,
            "workoutTargetTypeKey": "pace.zone",
            "displayOrder": 6,
        },
        "targetValueOne": _pace_to_mps(fast_pace, pace_unit_m),
        "targetValueTwo": _pace_to_mps(slow_pace, pace_unit_m),
    }


def _step_target(step: dict, pace_unit_m: float, pace_key: str, pace_fast_key: str, pace_slow_key: str) -> dict | None:
    if pace_key in step:
        # single pace -> +/-5 sec/unit band
        m, s = step[pace_key].split(":")
        center = int(m) * 60 + float(s)
        fast = f"{int(center - 5) // 60}:{int(center - 5) % 60:02d}"
        slow = f"{int(center + 5) // 60}:{int(center + 5) % 60:02d}"
        return _pace_target(fast, slow, pace_unit_m)
    if pace_fast_key in step and pace_slow_key in step:
        return _pace_target(step[pace_fast_key], step[pace_slow_key], pace_unit_m)
    return None


_STROKE_MAP = {
    # ids/keys confirmed empirically: Garmin's API silently corrects the
    # strokeTypeKey string to its own canonical value on upload, which
    # caught two wrong guesses here (id 6 is "free"/Freestyle, not "mixed"
    # as a reverse-engineered reference table had it; id 7 comes back as
    # "individual_medley"). Trust what Garmin echoes over any reference doc.
    "any": (1, "any_stroke"),
    "backstroke": (2, "backstroke"),
    "breaststroke": (3, "breaststroke"),
    "drill": (4, "drill"),
    "fly": (5, "fly"),
    "butterfly": (5, "fly"),
    "freestyle": (6, "free"),
    "free": (6, "free"),
    "im": (7, "individual_medley"),
    "medley": (7, "individual_medley"),
}


def _stroke_type(step: dict) -> dict | None:
    stroke = step.get("stroke")
    if not stroke:
        return None
    if stroke not in _STROKE_MAP:
        raise ValueError(f"Unknown stroke: {stroke!r}. Use one of {sorted(_STROKE_MAP)}")
    stroke_id, stroke_key = _STROKE_MAP[stroke]
    return {"strokeTypeId": stroke_id, "strokeTypeKey": stroke_key, "displayOrder": stroke_id}


def _end_condition(step: dict) -> tuple[dict, float]:
    if "send_off_s" in step:
        # "swim 100 on 1:45": rest for whatever's left of a fixed total
        # time per rep, not a flat rest duration. Must directly follow a
        # distance-based interval step inside the same repeat.
        return (
            {
                "conditionTypeId": ConditionType.FIXED_REPETITION,
                "conditionTypeKey": "fixed.repetition",
                "displayOrder": 9,
                "displayable": True,
            },
            float(step["send_off_s"]),
        )
    if "distance_m" in step:
        return (
            {
                "conditionTypeId": ConditionType.DISTANCE,
                "conditionTypeKey": "distance",
                "displayOrder": 3,
                "displayable": True,
            },
            float(step["distance_m"]),
        )
    if "duration_s" in step:
        return (
            {
                "conditionTypeId": ConditionType.TIME,
                "conditionTypeKey": "time",
                "displayOrder": 2,
                "displayable": True,
            },
            float(step["duration_s"]),
        )
    # lap-button fallback (e.g. "run until you're ready")
    return (
        {
            "conditionTypeId": ConditionType.LAP_BUTTON,
            "conditionTypeKey": "lap.button",
            "displayOrder": 1,
            "displayable": True,
        },
        0.0,
    )


_STEP_TYPE_MAP = {
    "warmup": (StepType.WARMUP, "warmup", 1),
    "cooldown": (StepType.COOLDOWN, "cooldown", 2),
    "interval": (StepType.INTERVAL, "interval", 3),
    "tempo": (StepType.INTERVAL, "interval", 3),
    "long": (StepType.INTERVAL, "interval", 3),
    "recovery": (StepType.RECOVERY, "recovery", 4),
    "rest": (StepType.REST, "rest", 5),
}


def _build_step(
    step: dict,
    order: int,
    pace_unit_m: float = 1000.0,
    pace_key: str = "pace",
    pace_fast_key: str = "pace_fast",
    pace_slow_key: str = "pace_slow",
) -> ExecutableStep | RepeatGroup:
    kind = step["type"]

    if kind == "repeat":
        inner = []
        n = order
        for s in step["steps"]:
            n += 1
            inner.append(_build_step(s, n, pace_unit_m, pace_key, pace_fast_key, pace_slow_key))
        return RepeatGroup(
            stepOrder=order,
            stepType={"stepTypeId": StepType.REPEAT, "stepTypeKey": "repeat", "displayOrder": 6},
            numberOfIterations=int(step["count"]),
            workoutSteps=inner,
            endCondition={
                "conditionTypeId": ConditionType.ITERATIONS,
                "conditionTypeKey": "iterations",
                "displayOrder": 7,
                "displayable": False,
            },
            endConditionValue=float(step["count"]),
        )

    if kind not in _STEP_TYPE_MAP:
        raise ValueError(f"Unknown step type: {kind!r}")
    step_type_id, step_type_key, display_order = _STEP_TYPE_MAP[kind]
    condition, condition_value = _end_condition(step)
    target = _step_target(step, pace_unit_m, pace_key, pace_fast_key, pace_slow_key)
    target_type = (target or {}).get("targetType") or {
        "workoutTargetTypeId": TargetType.NO_TARGET,
        "workoutTargetTypeKey": "no.target",
        "displayOrder": 1,
    }
    return ExecutableStep(
        stepOrder=order,
        stepType={"stepTypeId": step_type_id, "stepTypeKey": step_type_key, "displayOrder": display_order},
        endCondition=condition,
        endConditionValue=condition_value,
        targetType=target_type,
        targetValueOne=target.get("targetValueOne") if target else None,
        targetValueTwo=target.get("targetValueTwo") if target else None,
        strokeType=_stroke_type(step),
    )


@mcp.tool
def create_running_workout(
    name: str,
    steps: str,
    schedule_date: str | None = None,
) -> str:
    """
    Build a structured running workout and upload it to Garmin Connect so it
    syncs to your watch as a guided, step-by-step session.

    Args:
        name: Workout title, e.g. "Speed - 6x400m".
        steps: JSON array of step objects, in order. Each step is one of:
            {"type": "warmup", "duration_s": 600}
            {"type": "cooldown", "duration_s": 600}
            {"type": "recovery", "distance_m": 400}                 (or duration_s)
            {"type": "interval", "distance_m": 400, "pace_fast": "4:25", "pace_slow": "4:35"}
            {"type": "tempo", "duration_s": 1200, "pace": "5:15"}    (+/-5s/km band)
            {"type": "long", "distance_m": 14000, "pace_fast": "5:55", "pace_slow": "6:10"}
            {"type": "repeat", "count": 6, "steps": [ ...nested interval/recovery steps... ]}
          "pace" fields are "M:SS" per km. Omit pace entirely for an
          untargeted step (e.g. an easy warmup/cooldown/recovery).
        schedule_date: Optional ISO date (YYYY-MM-DD) to place this workout
            on your Garmin calendar for that day. Omit to just upload it
            unscheduled (pick it manually on the watch/app).
    """
    step_list = json.loads(steps)
    built = []
    order = 0
    for s in step_list:
        order += 1
        built.append(_build_step(s, order))

    total_secs = 0
    for s in step_list:
        if s["type"] == "repeat":
            per_iter = sum(inner.get("duration_s", 0) for inner in s["steps"])
            total_secs += per_iter * s["count"]
        else:
            total_secs += s.get("duration_s", 0)

    workout = RunningWorkout(
        workoutName=name,
        estimatedDurationInSecs=int(total_secs),
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
                workoutSteps=built,
            )
        ],
    )

    client = get_client()
    result = client.upload_running_workout(workout)

    if schedule_date:
        workout_id = result.get("workoutId") or result.get("workoutId".upper())
        if workout_id:
            client.schedule_workout(workout_id, schedule_date)

    return json.dumps(result, indent=2)


@mcp.tool
def create_swimming_workout(
    name: str,
    steps: str,
    pool_length_m: float = 25.0,
    schedule_date: str | None = None,
) -> str:
    """
    Build a structured pool swimming workout and upload it to Garmin Connect
    so it syncs to your watch as a guided, step-by-step session.

    Args:
        name: Workout title, e.g. "Free - 4x100m".
        steps: JSON array of step objects, in order. Each step is one of:
            {"type": "warmup", "duration_s": 300}                     (or distance_m)
            {"type": "cooldown", "distance_m": 100}
            {"type": "recovery", "distance_m": 25}                    (or duration_s)
            {"type": "rest", "duration_s": 20}
            {"type": "rest", "send_off_s": 105}                        ("100 on 1:45" send-off:
             rest for whatever's left of a fixed 105s per rep, not a flat
             20s rest. Must directly follow a distance-based interval step
             inside the same repeat.)
            {"type": "interval", "distance_m": 100, "stroke": "freestyle",
             "pace_fast_per_100": "1:40", "pace_slow_per_100": "1:45"}
            {"type": "interval", "distance_m": 50, "stroke": "backstroke",
             "pace_per_100": "1:50"}                                  (+/-5s/100m band)
            {"type": "repeat", "count": 4, "steps": [ ...nested interval/recovery steps... ]}
          "pace_per_100"/"pace_fast_per_100"/"pace_slow_per_100" are "M:SS"
          per 100m. Omit pace entirely for an untargeted step. "stroke" is
          one of: any (swimmer's choice), freestyle, backstroke,
          breaststroke, drill, fly (butterfly), im (individual medley,
          also: medley); omit for
          warmup/cooldown/unstroked steps.
        pool_length_m: Pool length in meters (25 = short course, 50 = long
            course). Defaults to 25.
        schedule_date: Optional ISO date (YYYY-MM-DD) to place this workout
            on your Garmin calendar for that day. Omit to just upload it
            unscheduled (pick it manually on the watch/app).
    """
    step_list = json.loads(steps)
    built = []
    order = 0
    for s in step_list:
        order += 1
        built.append(_build_step(s, order, 100.0, "pace_per_100", "pace_fast_per_100", "pace_slow_per_100"))

    total_secs = 0
    for s in step_list:
        if s["type"] == "repeat":
            per_iter = sum(inner.get("duration_s", inner.get("send_off_s", 0)) for inner in s["steps"])
            total_secs += per_iter * s["count"]
        else:
            total_secs += s.get("duration_s", s.get("send_off_s", 0))

    pool_unit = {"unitId": 1, "unitKey": "meter", "factor": 100.0}
    workout = SwimmingWorkout(
        workoutName=name,
        estimatedDurationInSecs=int(total_secs),
        poolLength=pool_length_m,
        poolLengthUnit=pool_unit,
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 4, "sportTypeKey": "swimming", "displayOrder": 3},
                workoutSteps=built,
                poolLength=pool_length_m,
                poolLengthUnit=pool_unit,
            )
        ],
    )

    client = get_client()
    result = client.upload_swimming_workout(workout)

    if schedule_date:
        workout_id = result.get("workoutId") or result.get("workoutId".upper())
        if workout_id:
            client.schedule_workout(workout_id, schedule_date)

    return json.dumps(result, indent=2)


@mcp.tool
def list_workouts(start: int = 0, limit: int = 20) -> str:
    """
    List saved workout templates (not calendar placements).

    Args:
        start: Offset to start from (default 0).
        limit: Max number of workouts to return (default 20).
    """
    result = get_client().get_workouts(start, limit)
    return json.dumps(result, indent=2)


@mcp.tool
def delete_workout(workout_id: int) -> str:
    """
    Delete a workout template from the workout library. Also removes any
    calendar placements of it.

    Args:
        workout_id: The workout's id, e.g. from create_running_workout's
            result or list_workouts.
    """
    result = get_client().delete_workout(workout_id)
    return json.dumps(result, indent=2)


@mcp.tool
def unschedule_workout(scheduled_workout_id: int) -> str:
    """
    Remove a workout from the calendar for the date it was scheduled on,
    without deleting the workout template itself.

    Args:
        scheduled_workout_id: The id of the calendar placement (distinct
            from the workout template's id) — from create_running_workout's
            schedule_workout result or get_scheduled_workouts.
    """
    result = get_client().unschedule_workout(scheduled_workout_id)
    return json.dumps(result, indent=2)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
