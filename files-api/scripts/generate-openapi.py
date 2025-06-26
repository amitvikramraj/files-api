# pylint: disable=invalid-name

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, NamedTuple, Union

from fastapi.openapi.utils import get_openapi
from files_api.main import create_app
from files_api.settings import Settings


@dataclass
class Diff:
    """A difference between two OpenAPI schemas."""

    path: str
    before: Union[str, dict, list, None]
    after: Union[str, dict, list, None]

    def __str__(self) -> str:
        before_str = "MISSING" if self.before is None else json.dumps(self.before, indent=2)
        after_str = "MISSING" if self.after is None else json.dumps(self.after, indent=2)
        return f"******** Diff at: {self.path}\nBEFORE: {before_str}\nAFTER: {after_str}"


class Args(NamedTuple):
    """CLI arguments for the script."""

    command: str
    output_spec: Path
    existing_spec: Union[Path, None]
    fail_on_diff: bool


def main() -> None:
    args = parse_args()

    if args.command == "generate":
        generated_openapi_schema = generate_openapi()
        write_openapi_to_disk(openapi_schema=generated_openapi_schema, outfile_path=args.output_spec)
        print("✅ Wrote OpenAPI schema to disk.")

    elif args.command == "generate-and-diff":
        generated_openapi_schema = generate_openapi()
        differences = get_diff_between_openapi_schemas(
            input_spec=args.existing_spec, generated_spec=generated_openapi_schema
        )
        schemas_match = not differences

        write_openapi_to_disk(openapi_schema=generated_openapi_schema, outfile_path=args.output_spec)
        print("✅ Wrote OpenAPI schema to disk.")

        if not schemas_match:
            print("❌ Existing OpenAPI schema does not match generated schema. Differences:\n")
            for difference in differences:
                print(difference)
                print()
            if args.fail_on_diff:
                sys.exit(1)


def parse_args() -> Args:
    """Parse command-line arguments.

    :return: Parsed command-line arguments as a NamedTuple.
    """
    parser = argparse.ArgumentParser(description="Generate OpenAPI schema from FastAPI app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser("generate", help="Generate OpenAPI schema")
    generate_parser.add_argument(
        "--output-spec",
        type=Path,
        help="Path to output the OpenAPI schema JSON file",
        required=True,
    )

    diff_parser = subparsers.add_parser("generate-and-diff", help="Generate and compare OpenAPI schema")
    diff_parser.add_argument(
        "--output-spec",
        type=Path,
        help="Path to output the OpenAPI schema JSON file",
        required=True,
    )
    diff_parser.add_argument(
        "--existing-spec",
        type=Path,
        help="Path to existing OpenAPI schema JSON file for comparison",
        required=True,
    )
    diff_parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Fail if there are differences between existing and generated schemas",
    )

    args = parser.parse_args()
    return Args(
        command=args.command,
        output_spec=args.output_spec,
        existing_spec=args.existing_spec if "existing_spec" in args else None,
        fail_on_diff=args.fail_on_diff if "fail_on_diff" in args else False,
    )


def generate_openapi() -> dict:
    """Generate the OpenAPI schema from the FastAPI app.

    Official docs for generating the FastAPI schema:
    https://fastapi.tiangolo.com/how-to/extending-openapi/?h=get_open#generate-the-openapi-schema

    :return: The generated OpenAPI schema.
    """
    settings = Settings(s3_bucket_name="placeholder")
    app = create_app(settings=settings)

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        summary=app.summary,
        description=app.description,
        tags=app.openapi_tags,
        servers=app.servers,
        license_info=app.license_info,
        contact=app.contact,
        terms_of_service=app.terms_of_service,
        routes=app.routes,
    )

    return openapi_schema


def write_openapi_to_disk(openapi_schema: dict, outfile_path: Path) -> None:
    """Write the OpenAPI schema to disk.

    :param openapi_schema: The OpenAPI schema to write to disk.
    :param outfile_path: The path to the output file.
    """
    outfile_path.write_text(json.dumps(openapi_schema, indent=2))


def get_diff_between_openapi_schemas(input_spec: Path, generated_spec: dict) -> List[Diff]:
    """Get the differences between the input and generated OpenAPI schemas.

    :param input_spec: The path to the input OpenAPI schema JSON file.
    :param generated_spec: The generated OpenAPI schema.
    :return: A list of differences between the input and generated schemas.
    """
    if not input_spec.exists():
        input_data = {}
    else:
        input_data = json.loads(input_spec.read_text())

    return list(diff_dicts(dict_a=input_data, dict_b=generated_spec))


def diff_dicts(dict_a: dict, dict_b: dict, path: str = "") -> Generator[Diff, None, None]:  # noqa: R701
    """Yield the differences between two dictionaries.

    :param d1: The first dictionary to compare.
    :param d2: The second dictionary to compare.
    :param path: The base path for nested keys.
    :yield: A generator yielding the differences as Diff objects.
    """
    for k in dict_a.keys() | dict_b.keys():
        current_path = f"{path}.{k}".lstrip(".")
        if k in dict_a and k not in dict_b:
            yield Diff(path=current_path, before=dict_a[k], after=None)
        elif k not in dict_a and k in dict_b:
            yield Diff(path=current_path, before=None, after=dict_b[k])
        elif isinstance(dict_a[k], dict) and isinstance(dict_b[k], dict):
            yield from diff_dicts(dict_a=dict_a[k], dict_b=dict_b[k], path=current_path)
        elif isinstance(dict_a[k], list) and isinstance(dict_b[k], list):
            yield from diff_lists(list_a=dict_a[k], list_b=dict_b[k], path=current_path)
        elif dict_a[k] != dict_b[k]:
            yield Diff(path=current_path, before=dict_a[k], after=dict_b[k])


def diff_lists(list_a: list, list_b: list, path: str) -> Generator[Diff, None, None]:
    """Yield the differences between two lists.

    :param l1: The first list to compare.
    :param l2: The second list to compare.
    :param path: The base path for nested indices.
    :yield: A generator yielding the differences as Diff objects.
    """
    for i, (item1, item2) in enumerate(zip(list_a, list_b)):
        current_path = f"{path}[{i}]"
        if isinstance(item1, dict) and isinstance(item2, dict):
            yield from diff_dicts(dict_a=item1, dict_b=item2, path=current_path)
        elif item1 != item2:
            yield Diff(path=current_path, before=item1, after=item2)

    if len(list_a) > len(list_b):
        for i in range(len(list_b), len(list_a)):
            current_path = f"{path}[{i}]"
            yield Diff(path=current_path, before=list_a[i], after=None)
    elif len(list_b) > len(list_a):
        for i in range(len(list_a), len(list_b)):
            current_path = f"{path}[{i}]"
            yield Diff(path=current_path, before=None, after=list_b[i])


if __name__ == "__main__":
    main()
