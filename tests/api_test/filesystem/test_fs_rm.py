import json
import time
import uuid

# mkdir queues background work on the new directory (its metadata embedding),
# so an immediate rm can get a retryable 409 while that work holds the path.
RM_RETRY_DEADLINE_SECS = 30.0
RM_RETRY_INTERVAL_SECS = 0.5


def is_retryable_conflict(response):
    if response.status_code != 409:
        return False
    error = response.json().get("error") or {}
    return bool((error.get("details") or {}).get("retryable"))


def rm_retrying_busy_path(api_client, uri):
    deadline = time.monotonic() + RM_RETRY_DEADLINE_SECS
    while True:
        response = api_client.fs_rm(uri, recursive=True)
        if not is_retryable_conflict(response) or time.monotonic() >= deadline:
            return response
        time.sleep(RM_RETRY_INTERVAL_SECS)


class TestFsRm:
    def test_fs_rm(self, api_client):
        random_id = str(uuid.uuid4())[:8]
        test_dir = f"viking://resources/test-rm-{random_id}"

        try:
            response = api_client.fs_mkdir(test_dir)
            print(f"\nCreate test directory API status code: {response.status_code}")
            assert response.status_code == 200, (
                f"Failed to create test directory: {response.status_code}"
            )

            response = rm_retrying_busy_path(api_client, test_dir)
            print(f"\nFS rm API status code: {response.status_code}")

            data = response.json()
            print("\n" + "=" * 80)
            print("FS Rm API Response:")
            print("=" * 80)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print("=" * 80 + "\n")

            assert data.get("status") == "ok", f"Expected status 'ok', got {data.get('status')}"
            assert data.get("error") is None, f"Expected error to be null, got {data.get('error')}"

        except Exception as e:
            print(f"Error: {e}")
            raise
