#!/bin/bash

set -e

#####################
# --- Constants --- #
#####################

AWS_PROFILE="cloud-course"
# AWS_REGION="ap-south-1"
AWS_REGION="us-west-2"
AWS_DEFAULT_REGION="$AWS_REGION"

THIS_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
MINIMUM_TEST_COVERAGE_PERCENT=0

AWS_LAMBDA_FUNCTION_NAME="files-api-handler"
BUILD_DIR_REL_PATH="./build"
BUILD_DIR="${THIS_DIR}/${BUILD_DIR_REL_PATH}"

##########################
# --- Task Functions --- #
##########################

# install core and development Python dependencies into the currently activated venv
function install {
	# python -m pip install --upgrade pip
	# python -m pip install --editable "$THIS_DIR/[dev]"
	uv sync --all-extras
}


# package and deploy the src/ code by updating an existing AWS Lambda function
# The function package consists of
# - deployment package: contents of the src/ folder
# - layer package: installed dependencies
#
# Note, this function assumes that
# - a lambda function named $AWS_LAMBDA_FUNCTION_NAME already exists
# - docker 🐳 is required to run this function

function set-local-aws-env-vars {
    export AWS_PROFILE
    export AWS_REGION
	export AWS_DEFAULT_REGION
}

function deploy-lambda {
	set-local-aws-env-vars
	deploy-lambda:cd
}

function deploy-lambda:cd {
	# Get the current user ID and group ID to run the docker command with so that
	# the generated lambda-env folder doesn't have root permissions, instead user level permission
	# This will help in library installation in the docker container and cleaning up the lambda-env folder later on.
	USER_ID=$(id -u)
	GROUP_ID=$(id -g)

	LAMBDA_LAYER_DIR_NAME="lambda-env"
	LAMBDA_LAYER_DIR="${BUILD_DIR}/${LAMBDA_LAYER_DIR_NAME}"
	LAMBDA_LAYER_ZIP_FPATH="${BUILD_DIR}/lambda-layer.zip"
	LAMBDA_HANDLER_ZIP_FPATH="${BUILD_DIR}/lambda.zip"
	SRC_DIR="${THIS_DIR}/src"

	# clean up artifacts
	rm -rf "$LAMBDA_LAYER_DIR" || true
	rm -f "$LAMBDA_LAYER_ZIP_FPATH" || true

	# install dependencies
	docker logout || true  # log out to use the public ecr
	docker pull public.ecr.aws/lambda/python:3.12-arm64

	# install dependencies in a docker container to ensure compatibility with AWS Lambda
	#
	# Note: we remote boto3 and botocore because AWS lambda automatically
	# provides these. This saves us ~24MB in the final, uncompressed layer size.
	docker run --rm \
		--user $USER_ID:$GROUP_ID \
		--volume "${THIS_DIR}":/out \
		--entrypoint /bin/bash \
		public.ecr.aws/lambda/python:3.12-arm64 \
		-c " \
		pip install --root --upgrade pip \
		&& pip install \
			--editable /out/[aws-lambda] \
			--target /out/${BUILD_DIR_REL_PATH}/${LAMBDA_LAYER_DIR_NAME}/python \
		"
	# && rm -rf /out/${BUILD_DIR_REL_PATH}/${LAMBDA_LAYER_DIR_NAME}/python/boto3 \
	# && rm -rf /out/${BUILD_DIR_REL_PATH}/${LAMBDA_LAYER_DIR_NAME}/python/botocore \

	# bundle dependencies and handler in a zip file
	cd "$LAMBDA_LAYER_DIR"
	zip -r "$LAMBDA_LAYER_ZIP_FPATH" ./ --exclude "*.pyc" --exclude "__pycache__/*"

	cd "$SRC_DIR"
	zip -r "$LAMBDA_HANDLER_ZIP_FPATH" ./ --exclude "*.pyc" --exclude "__pycache__/*"

	cd "$THIS_DIR"

	# publish the lambda "deployment package" (the handler)
	aws lambda update-function-code \
		--function-name "$AWS_LAMBDA_FUNCTION_NAME" \
		--zip-file fileb://${LAMBDA_HANDLER_ZIP_FPATH} \
		--output json | cat

	# publish the lambda layer with a new version
	LAYER_VERSION_ARN=$(aws lambda publish-layer-version \
		--layer-name cloud-course-project-python-deps \
		--compatible-runtimes python3.12 \
		--zip-file fileb://${LAMBDA_LAYER_ZIP_FPATH} \
		--compatible-architectures arm64 \
		--query 'LayerVersionArn' \
		--output text | cat)

	# update the lambda function to use the new layer version
	aws lambda update-function-configuration \
		--function-name "$AWS_LAMBDA_FUNCTION_NAME" \
		--layers $LAYER_VERSION_ARN \
		--handler "files_api.aws_lambda_handler.handler" \
		--output json | cat

	# update FilesAPIDashboard with the new version annotation
	update-dashboard
}


function deploy-lambda:code {
	# Function to deploy the application code to the lambda function
	set-local-aws-env-vars

	LAMBDA_HANDLER_ZIP_FPATH="${BUILD_DIR}/lambda.zip"
	SRC_DIR="${THIS_DIR}/src"

	# create the build directory if it doesn't exist
	[ ! -d "$BUILD_DIR" ] && mkdir -p "$BUILD_DIR"

	# clean up artifacts
	rm -f "$LAMBDA_HANDLER_ZIP_FPATH" || true

	# bundle handler code in a zip file
	cd "$SRC_DIR"
	zip -r "$LAMBDA_HANDLER_ZIP_FPATH" ./

	cd "$THIS_DIR"

	# publish the lambda "deployment package" (the handler)
	aws lambda update-function-code \
		--function-name "$AWS_LAMBDA_FUNCTION_NAME" \
		--zip-file fileb://${LAMBDA_HANDLER_ZIP_FPATH} \
		--output json | cat

	# update FilesAPIDashboard with the new version annotation
	update-dashboard
}


function update-dashboard {
	set-local-aws-env-vars

	VERSION_TXT_PATH=$THIS_DIR/version.txt
	DASHBOARD_NAME="FilesAPIDashboard"

	# Function to update the CloudWatch dashboard
	python3 "$THIS_DIR/scripts/update_dashboard.py" \
		--dashboard-name "$DASHBOARD_NAME" \
		--version-txt-path "$VERSION_TXT_PATH"

	echo "Dashboard updated successfully with version $(cat $VERSION_TXT_PATH)"
}

# start the FastAPI app locally with real AWS credentials
function run {
	AWS_PROFILE=$AWS_PROFILE\
	S3_BUCKET_NAME=python-aws-cloud-course-bucket\
	uvicorn 'files_api.main:create_app' --factory --host 0.0.0.0 --port 8000 --reload
}


# start the FastAPI app in a Docker container
function run-docker {
    aws configure export-credentials --profile $AWS_PROFILE --format env > .env
    set-local-aws-env-vars
    docker compose up --remove-orphans --build
}

# Run with Locust
function run-locust {
    set-local-aws-env-vars
    aws configure export-credentials --profile $AWS_PROFILE --format env > .env
    docker compose \
        --file docker-compose.yaml \
        --file docker-compose.locust.yaml \
        up \
        --build
}


# start the FastAPI app locally with actual AWS & OpenAI credentials
function run-local {
	if [ ! -f "$THIS_DIR/.openai-env" ]; then
        echo "No OpenAI environment file found. Please create a .openai-env file with the OpenAI API key."
        return 1
    fi

	AWS_PROFILE=$AWS_PROFILE\
	S3_BUCKET_NAME=python-aws-cloud-course-bucket\
	uvicorn 'files_api.main:create_app' --factory --host 0.0.0.0 --port 8000 --reload

	# Unset the environment variables
	unset OPENAI_API_KEY
}

# start the FastAPI app, pointed at a mocked aws endpoint
function run-mock {
	set -e

	# Check if Docker is running
	if ! docker info >/dev/null 2>&1; then
		echo "Docker is not running. Please start Docker Desktop and try again."
		exit 1
	fi

	#####################################
    # --- Mock AWS with Moto server --- #
    #####################################

	# Start moto.server in the background on localhost:5001
	MOTO_PORT=5001
	python -m moto.server -p $MOTO_PORT &
	MOTO_PID=$!

	# point the AWS CLI and boto3 to the mocked AWS server using mocked credentials
	export AWS_ENDPOINT_URL="http://localhost:$MOTO_PORT"
	export AWS_SECRET_ACCESS_KEY="mock"
	export AWS_ACCESS_KEY_ID="mock"
	export S3_BUCKET_NAME="some-bucket"

	# create a bucket called "some-bucket" using the mocked aws server
	aws s3 mb "s3://$S3_BUCKET_NAME"

	#######################################
    # --- Mock OpenAI with mockserver --- #
    #######################################

	# point the OpenAI API to the mocked OpenAI server using mocked credentials
	export OPENAI_MOCK_PORT=1080
	export OPENAI_BASE_URL="http://localhost:$OPENAI_MOCK_PORT"
	export OPENAI_API_KEY="mocked_key"

    python "$THIS_DIR/tests/mocks/openai_fastapi_mock_app.py" &
    OPENAI_MOCK_PID=$!

	###########################################################
    # --- Schedule the mocks to shut down on FastAPI Exit --- #
    ###########################################################

    # Trap EXIT signal to kill the moto.server and mocked open-ai server process when uvicorn stops
    trap "kill $MOTO_PID; kill $OPENAI_MOCK_PID" EXIT

    # ----- #
	# OLD OpenAI Mocking

	# # Start the Docker Compose to mock the OpenAI API
	# docker compose --file ./mock-openai-docker-compose.yaml up --detach

	# # Trap EXIT signal to kill the moto.server process when uvicorn stops
	# trap "kill $MOTO_PID; docker compose --file ./mock-openai-docker-compose.yaml down" EXIT

	# ----- #

	# Export Log Level
	export LOGURU_LEVEL="DEBUG"

	# Disable AWS X-Ray
	export AWS_XRAY_SDK_ENABLED="false"

	# Export AWS EMF Environment Variables
	export AWS_EMF_DISABLE_METRIC_EXTRACTION="true"	# Disable EMF
	export AWS_EMF_ENVIRONMENT=local # causes metrics to go to stdout
    export AWS_EMF_ENABLE_DEBUG_LOGGING="true"
    export AWS_EMF_NAMESPACE=local-fastapi-service

	# Start FastAPI app with uvicorn in the foreground
	uvicorn src.files_api.main:create_app --factory --host 0.0.0.0 --port 8000 --reload

	# Wait for the moto.server process to finish (this is optional if you want to keep it running)
	wait $MOTO_PID
	wait $OPENAI_MOCK_PID
}


function install-generated-sdk {
	# install the generated SDK in newly created venv
	uv pip install --upgrade pip
	uv pip install --editable "$THIS_DIR/files-api-sdk/" \
		--config-settings editable_mode=strict
}


function generate-client-library {
	# Get the current user ID and group ID to run the docker command with so that
	# the generated SDK folder doesn't have root permissions, instead user level permission
	USER_ID=$(id -u)
	GROUP_ID=$(id -g)

	docker run --rm \
		--user $USER_ID:$GROUP_ID \
		-v $PWD:/local openapitools/openapi-generator-cli generate \
		--generator-name python-pydantic-v1 \
		--input-spec /local/openapi.json \
		--output /local/files-api-sdk \
		--package-name files_api_sdk
}


# run linting, formatting, and other static code quality tools
function lint {
	uvx --from pre-commit pre-commit run --all-files
}

# same as `lint` but with any special considerations for CI
function lint:ci {
	# We skip no-commit-to-branch since that blocks commits to `main`.
	# All merged PRs are commits to `main` so this must be disabled.
	SKIP=no-commit-to-branch lint
}

# execute tests that are not marked as `slow`
function test:quick {
	run-tests -m "not slow" ${@:-"$THIS_DIR/tests/"}
}

# execute tests against the installed package; assumes the wheel is already installed
function test:ci {
	INSTALLED_PKG_DIR="$(python -c 'import files_api; print(files_api.__path__[0])')"
	# in CI, we must calculate the coverage for the installed package, not the src/ folder
	COVERAGE_DIR="$INSTALLED_PKG_DIR" run-tests
}

# (example) ./run.sh test tests/test_states_info.py::test__slow_add
function run-tests {
	PYTEST_EXIT_STATUS=0

	# Disable AWS X-Ray and AWS EMF
	export AWS_XRAY_SDK_ENABLED="false"
	export AWS_EMF_DISABLE_METRIC_EXTRACTION="true"	# Disable EMF

	# clean the test-reports dir
	rm -rf "$THIS_DIR/test-reports" || mkdir "$THIS_DIR/test-reports"

	# execute the tests, calculate coverage, and generate coverage reports in the test-reports dir
	uv run pytest ${@:-"$THIS_DIR/tests/"} \
		--cov "${COVERAGE_DIR:-$THIS_DIR/src}" \
		--cov-report html \
		--cov-report term \
		--cov-report xml \
		--junit-xml "$THIS_DIR/test-reports/report.xml" \
		--cov-fail-under "$MINIMUM_TEST_COVERAGE_PERCENT" || ((PYTEST_EXIT_STATUS+=$?))
	mv coverage.xml "$THIS_DIR/test-reports/" || true
	mv htmlcov "$THIS_DIR/test-reports/" || true
	mv .coverage "$THIS_DIR/test-reports/" || true
	return $PYTEST_EXIT_STATUS
}

function test:wheel-locally {
	source deactivate || true
	rm -rf test-env || true
	uv venv test-env
	source test-env/bin/activate
	clean || true
	build
	WHEEL_FPATH=$(ls ./dist/*.whl)
	uv pip install "${WHEEL_FPATH}[test]" || true
	test:ci || true
	source deactivate || true
	rm -rf test-env || true
	clean || true
}

# serve the html test coverage report on localhost:8000
function serve-coverage-report {
	uv run python -m http.server --directory "$THIS_DIR/test-reports/htmlcov/" 8000
}

# build a wheel and sdist from the Python source code
function build {
	uv build --sdist --wheel "$THIS_DIR/"
}

function release:test {
	lint
	clean
	build
	publish:test
}

function release:prod {
	release:test
	publish:prod
}

function publish:test {
	try-load-dotenv || true
	twine upload dist/* \
		--repository testpypi \
		--username=__token__ \
		--password="$TEST_PYPI_TOKEN"
}

function publish:prod {
	try-load-dotenv || true
	twine upload dist/* \
		--repository pypi \
		--username=__token__ \
		--password="$PROD_PYPI_TOKEN"
}

# remove all files generated by tests, builds, or operating this codebase
function clean {
	rm -rf dist build coverage.xml test-reports
	find . \
	  -type d \
	  \( \
		-name "*cache*" \
		-o -name "*.dist-info" \
		-o -name "*.egg-info" \
		-o -name "*htmlcov" \
	  \) \
	  -not -path "*env*/*" \
	  -exec rm -r {} + || true

	find . \
	  -type f \
	  -name "*.pyc" \
	  -not -path "*env/*" \
	  -exec rm {} +
}

# export the contents of .env as environment variables
function try-load-dotenv {
	if [ ! -f "$THIS_DIR/.env" ]; then
		echo "no .env file found"
		return 1
	fi

	while read -r line; do
		export "$line"
	done < <(grep -v '^#' "$THIS_DIR/.env" | grep -v '^$')
}

# print all functions in this file
function help {
	echo "$0 <task> <args>"
	echo "Tasks:"
	compgen -A function | cat -n
}

TIMEFORMAT="Task completed in %3lR"
time ${@:-help}
