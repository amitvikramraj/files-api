#!/bin/bash -ex

########################
# --- Change these --- #
########################

PROJECT_NAME=cdk-infra
PACKAGE_NAME=files_api_cdk
PYTHON_VERSION=3.12
AWS_PROFILE=sbox

# ----------------------

ROOT_DIR="$(pwd)"
PROJECT_DIR="${ROOT_DIR}/${PROJECT_NAME}"

# temp dir: we'll create a boilerplate project here. PACKAGE_NAME is in the name so that the generated
# boilerplate files have the right names.
TEMP_DIR="${ROOT_DIR}/temp/${PACKAGE_NAME}"

# create the uv project where our CDK code will go
uv init "$PROJECT_DIR" --lib --python "$PYTHON_VERSION" --no-workspace --name "$PACKAGE_NAME" --vcs="none"

# generate a boilerplate CDK project in a temp dir so we can copy select boilerplate files
mkdir -p "$TEMP_DIR"
pushd "$TEMP_DIR"
# --profile: Use the indicated AWS profile as the default environment
# --generate-only: If true, only generates project files, without executing additional operations
# such as setting up a git repo, installing dependencies or compiling the project
cdk init --language python --generate-only="true" --profile "$AWS_PROFILE"
popd

# the generated file structure from the `cdk init` command looks like this:
# .
# ├── server_infra
# │  ├── server_infra_stack.py           # we want this
# │  └── __init__.py
# ├── tests
# │  ├── unit
# │  │  ├── __init__.py
# │  │  └── test_server_infra_stack.py
# │  └── __init__.py
# ├── .gitignore                         # we want this
# ├── cdk.json                           # we want this
# ├── app.py                             # we want this
# ├── README.md
# ├── requirements-dev.txt
# ├── requirements.txt                   # we want to add these to pyproject.toml:dependencies
# └── source.bat

# move some select files
mv "$TEMP_DIR/app.py" "$PROJECT_DIR/app.py"
mv "$TEMP_DIR/cdk.json" "$PROJECT_DIR/cdk.json"
# Append the CDK .gitignore to the uv .gitignore
cat "$TEMP_DIR/.gitignore" >> "$PROJECT_DIR/.gitignore"
mv "$TEMP_DIR/${PACKAGE_NAME}/${PACKAGE_NAME}_stack.py" "${PROJECT_DIR}/src/${PACKAGE_NAME}/${PACKAGE_NAME}_stack.py"

# add the requirements.txt
pushd "$PROJECT_DIR"
uv add -r "$TEMP_DIR/requirements.txt"
popd

# we don't need the temp dir anymore since we've copied the boilerplate we care about
rm -rf temp
