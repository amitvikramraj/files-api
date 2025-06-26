import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3

try:
    from mypy_boto3_cloudwatch import CloudWatchClient
    from mypy_boto3_cloudwatch.type_defs import GetDashboardOutputTypeDef
except ImportError:
    ...


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="update_dashboard", description="Update Files API Dashboard in Cloudwatch.")
    parser.add_argument("--dashboard-name", required=True, help="Name of the CloudWatch dashboard.")
    (parser.add_argument("--version-txt-path", required=True, help="Path to the version.txt file."),)
    parser.add_argument(
        "--n-deployment-events",
        type=int,
        default=10,
        required=False,
        help="Number of deployment events to keep for the annotations.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset the dashboard widgets, i.e. remove all vertical annotations.",
    )
    return parser.parse_args()


def update_dashboard_widgets(
    dashboard_name: str,
    version_txt_path: Path,
    n_deployment_events: int | None = None,
    reset: bool = False,
    cloudwatch_client: "CloudWatchClient" = None,
) -> None:
    """Update the dashboard widgets with vertical line for the deployment version.

    Args:
        :cloudwatch_client: CloudWatchClient: The CloudWatch client
        :dashboard_name: str: The name of the dashboard
        :verion_txt_path: Path: The path to the version.txt file
        :n_deployment_events: int: The number of deployment events to keep for the vertical annotations, default 10
        :reset: bool: Reset the dashboard widgets, i.e. remove all vertical annotations; default False

    returns: None

    """
    n_deployment_events = n_deployment_events or 10
    cloudwatch_client = cloudwatch_client or boto3.client("cloudwatch")
    response: "GetDashboardOutputTypeDef" = cloudwatch_client.get_dashboard(DashboardName=dashboard_name)

    dashboard_body: str = response.get("DashboardBody", "{}")
    dashboard_body: dict = json.loads(dashboard_body)  # type: ignore

    if reset:
        # reset dashboard widgets
        updated_dashboard_body = reset_dashboard_widgets(dashboard_body)  # type: ignore

    # update dashboard widgets
    updated_dashboard_body = add_vertical_annotations_to_widgets(
        dashboard_body=dashboard_body,  # type: ignore
        version_txt_path=version_txt_path,
        n_deployment_events=n_deployment_events,
    )

    # update the dashboard
    cloudwatch_client.put_dashboard(
        DashboardName=dashboard_name,
        DashboardBody=json.dumps(updated_dashboard_body),
    )


def get_deployment_verison(verion_txt_path: Path) -> str:
    """Get the deployment version from version.txt"""
    if not verion_txt_path.exists():
        raise FileNotFoundError(f"File not found: {verion_txt_path}")

    # read version.txt
    with open(verion_txt_path, "r") as f:  # pylint: disable=unspecified-encoding
        version = f.read().strip()
    return version


def add_vertical_annotations_to_widgets(
    dashboard_body: dict,
    version_txt_path: Path,
    n_deployment_events: int,
) -> dict:
    """Add a vertical annotation to all timeSeries widgets in the dashboard with the current deployment version.

    Args:
        :dashboard_body: dict: The dashboard body from CloudWatch
        :version_txt_path: Path: The path to the version.txt file
        :n_deployment_events: int: The number of deployment events to keep for the annotations
    Returns:
        :dict: The updated dashboard body

    """
    # get deployment version
    version = get_deployment_verison(version_txt_path)

    # get current time in ISO format, "2024-07-04T09:37:08.000Z"
    current_time = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    for widget in dashboard_body.get("widgets", []):
        widget_properties: dict = widget.get("properties") or dict()
        if widget_properties.get("view") == "timeSeries":
            # get annotations
            annotations: dict[str, list[dict]] = widget_properties.get("annotations") or dict()

            # add vertical annotation
            vertical_annotations = annotations.get("vertical") or list()

            # only keep last n deployments annotations
            vertical_annotations = vertical_annotations[-n_deployment_events:]
            vertical_annotations.append({"color": "#69ae34", "label": f"{version}", "value": current_time})

            # overwrite current annotations
            annotations["vertical"] = vertical_annotations
            widget_properties["annotations"] = annotations

    return dashboard_body


def reset_dashboard_widgets(dashboard_body: dict) -> dict:
    """Reset the dashboard widgets by removing all vertical annotations.

    Args:
        :dashboard_body: dict: The dashboard body from CloudWatch
    Returns:
        :dict: The updated dashboard body

    """
    for widget in dashboard_body.get("widgets", []):
        widget_properties: dict = widget.get("properties") or dict()
        if widget_properties.get("view") == "timeSeries":
            # get annotations
            annotations: dict[str, list[dict]] = widget_properties.get("annotations") or dict()
            vertical_annotations = annotations.get("vertical") or list()
            if vertical_annotations:
                annotations["vertical"] = []  # remove vertical annotations

            widget_properties["annotations"] = annotations

    return dashboard_body


if __name__ == "__main__":
    args = parse_args()
    update_dashboard_widgets(
        dashboard_name=args.dashboard_name,
        version_txt_path=Path(args.version_txt_path),
        n_deployment_events=args.n_deployment_events,
        reset=args.reset,
    )
