# coding: utf-8

from fastapi.testclient import TestClient


from pydantic import StrictBytes, StrictStr  # noqa: F401
from typing import Any, Tuple, Union  # noqa: F401
from bundler_server.models.bundle import Bundle  # noqa: F401
from bundler_server.models.create_bundle_request import CreateBundleRequest  # noqa: F401
from bundler_server.models.health_response import HealthResponse  # noqa: F401


def test_get_health_v1(client: TestClient):
    """Test case for get_health_v1

    Health check (v1)
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/v1/health",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_create_bundle_v1(client: TestClient):
    """Test case for create_bundle_v1

    Request a bundle (v1)
    """
    create_bundle_request = {"urls":["https://openapi-generator.tech","https://openapi-generator.tech"],"folder_name":"folderName","compression":"zip"}

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/v1/bundles",
    #    headers=headers,
    #    json=create_bundle_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_get_bundle_v1(client: TestClient):
    """Test case for get_bundle_v1

    Get bundle status (v1)
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/v1/bundles/{bundleId}".format(bundleId='bundle_id_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_download_bundle_v1(client: TestClient):
    """Test case for download_bundle_v1

    Download bundle archive (v1)
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/v1/bundles/{bundleId}/download".format(bundleId='bundle_id_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_get_health_v2(client: TestClient):
    """Test case for get_health_v2

    Health check (v2)
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/v2/health",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_create_bundle_v2(client: TestClient):
    """Test case for create_bundle_v2

    Request a bundle (v2)
    """
    create_bundle_request = {"urls":["https://openapi-generator.tech","https://openapi-generator.tech"],"folder_name":"folderName","compression":"zip"}

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/v2/bundles",
    #    headers=headers,
    #    json=create_bundle_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_get_bundle_v2(client: TestClient):
    """Test case for get_bundle_v2

    Get bundle status (v2)
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/v2/bundles/{bundleId}".format(bundleId='bundle_id_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_download_bundle_v2(client: TestClient):
    """Test case for download_bundle_v2

    Download bundle archive (v2)
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/v2/bundles/{bundleId}/download".format(bundleId='bundle_id_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_get_health(client: TestClient):
    """Test case for get_health

    Health check
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/health",
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_create_bundle(client: TestClient):
    """Test case for create_bundle

    Request a bundle to be created from presigned file URLs
    """
    create_bundle_request = {"urls":["https://openapi-generator.tech","https://openapi-generator.tech"],"folder_name":"folderName","compression":"zip"}

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/bundles",
    #    headers=headers,
    #    json=create_bundle_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_get_bundle(client: TestClient):
    """Test case for get_bundle

    Get bundle status
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/bundles/{bundleId}".format(bundleId='bundle_id_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_download_bundle(client: TestClient):
    """Test case for download_bundle

    Download the completed bundle archive
    """

    headers = {
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/bundles/{bundleId}/download".format(bundleId='bundle_id_example'),
    #    headers=headers,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

