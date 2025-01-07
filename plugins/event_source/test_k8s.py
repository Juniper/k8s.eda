import asyncio
import pytest
import time
from kubernetes import client, config

from plugins.event_source.k8s import (
    main,
    Watcher,
)


# Path to the kubeconfig file for the kind cluster
KUBECONFIG = ".pytest-kind/pytest-kind/kubeconfig"

# Timeout constants
INIT_DONE_TIMEOUT = 10
POD_TIMEOUT = 60
NAMESPACE_TIMEOUT = 10
HEARTBEAT_INTERVAL = 3


@pytest.fixture(scope="session")
def kind_cluster(kind_cluster):
    """
    Fixture to spin up a kind cluster for the duration of the session.
    """
    yield kind_cluster


@pytest.fixture(scope="session")
def k8s_client(kind_cluster):
    """
    Fixture to load kubeconfig and create a Kubernetes client.

    :param kind_cluster: The kind cluster fixture.
    :return: Kubernetes CoreV1Api client.
    """
    config.load_kube_config(
        str(kind_cluster.kubeconfig_path)
    )  # Convert PosixPath to string
    return client.CoreV1Api()


@pytest.fixture(scope="function", autouse=True)
def setup_namespace(request, k8s_client):
    """
    Fixture to set up the namespace for each test function.

    :param request: The pytest request object.
    :param k8s_client: The Kubernetes client fixture.
    """
    # Get the namespace from the command-line argument or use "pytest" as default
    namespace = request.config.getoption("--namespace")

    # Delete the namespace if it exists
    for ns in [namespace, "pytest-namespace"]:
        try:
            k8s_client.delete_namespace(name=ns)
            # Wait for the namespace to be deleted
            for _ in range(POD_TIMEOUT):  # Retry for POD_TIMEOUT seconds
                try:
                    k8s_client.read_namespace(name=ns)
                    time.sleep(1)
                except client.exceptions.ApiException as e:
                    if e.status == 404:
                        break  # Namespace is deleted
                    else:
                        raise
        except client.exceptions.ApiException as e:
            if e.status != 404:
                raise

    # Create the namespace
    namespace_manifest = {
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": namespace},
    }
    k8s_client.create_namespace(body=namespace_manifest)

    # Wait for the namespace to be created
    for _ in range(60):  # Retry for up to 60 seconds
        try:
            k8s_client.read_namespace(name=namespace)
            break  # Namespace is available
        except client.exceptions.ApiException:
            time.sleep(1)
    else:
        raise RuntimeError("Timeout waiting for namespace to be created")

    # Wait for the default service account to be created
    for _ in range(60):  # Retry for up to 60 seconds
        try:
            k8s_client.read_namespaced_service_account(
                name="default", namespace=namespace
            )
            break  # Service account is available
        except client.exceptions.ApiException:
            time.sleep(1)
    else:
        raise RuntimeError("Timeout waiting for service account to be created")

    return namespace


async def wait_for_event(
    queue, event_type=Watcher.INIT_DONE_EVENT, timeout=INIT_DONE_TIMEOUT
):
    """
    Wait for a specific event type to appear in the queue within a given timeout.

    Args:
        queue (asyncio.Queue): The queue to monitor for events.
        event_type (str): The type of event to wait for.
        timeout (int): The maximum time to wait for the event, in seconds.

    Returns:
        list: A list of events received before the specified event type.
        bool: False if the timeout is reached before the specified event type is received.

    Raises:
        asyncio.TimeoutError: If the timeout is reached before any event is received.
    """
    start_time = time.time()
    events = []
    try:
        # Wait for the INIT_DONE event with a timeout
        while True:
            event = await asyncio.wait_for(queue.get(), timeout)
            events.append(event)
            if event["type"] == event_type:
                return events
            if time.time() - start_time > timeout:
                return events
    except asyncio.TimeoutError:
        raise


pod_manifest = {
    "apiVersion": "v1",
    "kind": "Pod",
    "metadata": {
        "namespace": "pytest",
        "name": "example-pod",
        "labels": {
            "type": "eda",
        },
    },
    "spec": {
        "containers": [
            {
                "name": "example-container",
                "image": "busybox",
                "command": ["sleep", "1"],
            }
        ],
        "terminationGracePeriodSeconds": 0,  # Set a short termination grace period
    },
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "test_case",
    [
        {
            "args": {
                "api_version": "v1",
                "kind": "Namespace",
                "kubeconfig": KUBECONFIG,
                "test_events_qty": 1,
                "heartbeat_interval": HEARTBEAT_INTERVAL,
            },
            "k8sclient_objects": [
                {
                    "method": "create_namespace",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {"name": "pytest-namespace"},
                    },
                },
            ],
            "timeout": NAMESPACE_TIMEOUT,
        },
        {
            "args": {
                "kinds": [
                    {
                        "api_version": "v1",
                        "kind": "Namespace",
                    },
                    {
                        "api_version": "v1",
                        "kind": "ConfigMap",
                        "namespace": "pytest-namespace",
                    },
                ],
                "kubeconfig": KUBECONFIG,
                "test_events_qty": 3,
                "heartbeat_interval": HEARTBEAT_INTERVAL,
            },
            # An extra ConfigMap is created for the new Namespace
            "created_watch_count": 3,
            "k8sclient_objects": [
                {
                    "method": "create_namespace",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "Namespace",
                        "metadata": {"name": "pytest-namespace"},
                    },
                },
                {
                    "method": "create_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "example-configmap",
                            "namespace": "pytest-namespace",
                        },
                        "data": {
                            "key": "value",
                        },
                    },
                },
            ],
            "timeout": NAMESPACE_TIMEOUT * 2,
        },
        {
            "args": {
                "kind": "ConfigMap",
                "changed_fields": ["data", "metadata.annotations.foo"],
                "kubeconfig": KUBECONFIG,
                "test_events_qty": 6,
                "heartbeat_interval": HEARTBEAT_INTERVAL,
            },
            "created_watch_count": 2,
            "modified_watch_count": 3,
            "deleted_watch_count": 1,
            "k8sclient_objects": [
                {
                    "method": "create_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "change-me",
                            "namespace": "pytest",
                            "description": "CONFIG MAP TO MODIFY",
                            "annotations": {
                                "foo": "bar",
                            },
                        },
                        "data": {
                            "key": "old",
                        },
                    },
                },
                {
                    "method": "create_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "static",
                            "namespace": "pytest",
                            "description": "STATIC CONFIG MAP",
                        },
                        "data": {
                            "key": "no change ever",
                        },
                    },
                },
                {
                    "method": "patch_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "change-me",
                            "namespace": "pytest",
                            "description": "CHANGE 1",
                        },
                        "data": {
                            "key": "new",
                        },
                    },
                },
                {
                    "method": "patch_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "change-me",
                            "namespace": "pytest",
                            "description": "CHANGE 2",
                        },
                        "data": {
                            "key": "new2",
                        },
                    },
                },
                {
                    "method": "patch_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "static",
                            "namespace": "pytest",
                            # Description should trigger an event
                            "description": "ONLY UPDATING DESCRIPTION",
                        },
                    },
                },
                {
                    "method": "patch_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "static",
                            "namespace": "pytest",
                            # Annotations change should not trigger event
                            "annotations": {
                                "foo": "CHANGED",
                            },
                        },
                    },
                },
                {
                    "method": "delete_namespaced_config_map",
                    "body": {
                        "apiVersion": "v1",
                        "kind": "ConfigMap",
                        "metadata": {
                            "name": "static",
                            "namespace": "pytest",
                        },
                    },
                },
            ],
            "timeout": NAMESPACE_TIMEOUT * 7,
        },
        {
            "args": {
                "kind": "Pod",
                "changed_fields": ["metadata.resourceVersion"],
                "kubeconfig": KUBECONFIG,
                "test_events_qty": 4,
                "heartbeat_interval": HEARTBEAT_INTERVAL,
            },
            "created_watch_count": 1,
            "modified_watch_count": 2,
            "deleted_watch_count": 1,
            "k8sclient_objects": [
                {
                    "method": "create_namespaced_pod",
                    "body": pod_manifest,
                },
                {
                    "method": "delete_namespaced_pod",
                    "body": pod_manifest,
                },
            ],
            "timeout": POD_TIMEOUT * 2,
        },
        {
            "args": {
                "kind": "Pod",
                "changed_fields": ["metadata.resourceVersion"],
                "ignore_modified_deleted": True,
                "kubeconfig": KUBECONFIG,
                "test_events_qty": 3,
                "heartbeat_interval": HEARTBEAT_INTERVAL,
            },
            "created_watch_count": 1,
            "modified_watch_count": 1,
            "deleted_watch_count": 1,
            "k8sclient_objects": [
                {
                    "method": "create_namespaced_pod",
                    "body": pod_manifest,
                },
                {
                    "method": "delete_namespaced_pod",
                    "body": pod_manifest,
                },
            ],
            "timeout": POD_TIMEOUT * 2,
        },
    ],
    ids=[
        "create_namespace_kind",
        "create_namespace_configmap_kinds",
        "modify_configmap_changed_fields",
        "modify_deleted_pod",
        "ignore_modify_deleted_pod",
    ],
)
async def test_batch(k8s_client, test_case):
    """
    Test case to verify Kubernetes events are received correctly.

    :param k8s_client: The Kubernetes client fixture.
    :param test_case: The test case parameters.
    """
    # Use a real asyncio.Queue
    queue = asyncio.Queue()
    k8s_client.patch_namespaced_config_map
    # Run the main function in the background
    args = test_case["args"]
    assert args
    main_task = asyncio.create_task(main(queue, args))

    kinds = []
    if "kind" in args:
        kinds.append(args["kind"])
    if "kinds" in args:
        kinds.extend(args["kinds"])

    for _ in range(0, len(kinds)):
        # Wait for each watch to finish initializing
        events = await wait_for_event(
            queue, event_type=Watcher.INIT_DONE_EVENT, timeout=INIT_DONE_TIMEOUT
        )
        assert events
        assert len(events) == 1
        assert events[-1]["type"] == Watcher.INIT_DONE_EVENT

    k8sclient_objects = test_case["k8sclient_objects"]
    assert k8sclient_objects

    # Helper to invoke all object methods by name
    def call_methods():
        # Count the number of methods of each kind in the test case
        create_qty = 0
        modify_qty = 0
        delete_qty = 0

        for object in k8sclient_objects:
            method = object.get("method")
            if method:
                method_prefix = method.split("_", 1)[0]
                if method_prefix == "create":
                    create_qty += 1
                elif method_prefix == "patch":
                    modify_qty += 1
                elif method_prefix == "delete":
                    delete_qty += 1
                else:
                    assert method in ("create", 'patch", delete')

                body = object["body"]
                metadata = body["metadata"]
                namespace = metadata.get("namespace")
                name = metadata.get("name")

                kwargs = {}
                if namespace:
                    kwargs.update(namespace=namespace)
                if not method_prefix == "create":
                    kwargs.update(name=name)
                if method_prefix == "delete":
                    kwargs.update(grace_period_seconds=0)
                else:
                    kwargs.update(body=body)

                k8s_client_method = getattr(k8s_client, method)
                assert k8s_client_method
                k8s_client_method(**kwargs)

        return create_qty, modify_qty, delete_qty

    # Call the k8s_client methods in the test case
    create_qty, modify_qty, delete_qty = call_methods()

    # Wait for the main function to complete
    timeout = test_case.get("timeout", POD_TIMEOUT)
    await asyncio.wait_for(main_task, timeout=timeout)

    # Make we have the expected number of events in the queue
    queue_len = queue.qsize()
    test_events_qty = args["test_events_qty"]
    assert test_events_qty
    assert queue_len == test_events_qty

    # Ensure the correct number of kinds were created/added
    # Retrieve all items from the queue to get the last item
    added_count = 0
    modified_count = 0
    deleted_count = 0
    try:
        while True:
            event = queue.get_nowait()
            event_type = event["type"]
            assert event_type in ["ADDED", "MODIFIED", "DELETED"]
            if event_type == "ADDED":
                added_count += 1
            elif event_type == "MODIFIED":
                modified_count += 1
            elif event_type == "DELETED":
                deleted_count += 1

    except asyncio.QueueEmpty:
        pass

    assert added_count == test_case.get("created_watch_count", create_qty)
    assert modified_count == test_case.get("modified_watch_count", modify_qty)
    assert deleted_count == test_case.get("deleted_watch_count", delete_qty)
