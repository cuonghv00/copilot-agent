#!/usr/bin/env python3
"""Copilot Agent CLI — WebSocket server, repo packaging, verification."""
import json
import os
import subprocess
import zipfile
from pathlib import Path


def load_config():
    """Load configuration from config.json."""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path) as f:
        return json.load(f)


def zip_repo(repo_path: Path, output_zip: Path) -> Path:
    """Zip the repository using git archive for speed and respecting .gitignore.

    Args:
        repo_path: Path to the repository directory to zip.
        output_zip: Path where the zip file will be created.

    Returns:
        Path to the created zip file.
    """
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(f"git archive --format=zip HEAD -o {output_zip}", shell=True, cwd=repo_path)
    return output_zip


import asyncio
import websockets

def extract_zip(zip_path: Path, target_dir: Path) -> bool:
    """Extract a zip file into target_dir and delete the zip afterwards.

    Args:
        zip_path: Path to the zip file to extract.
        target_dir: Directory to extract files into.

    Returns:
        True if extraction succeeded, False otherwise.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(target_dir)
        zip_path.unlink()
        return True
    except (zipfile.BadZipFile, OSError) as e:
        print(f"[CLI] Extract error: {e}")
        return False


def run_verify(command: str, cwd: Path) -> tuple[bool, str]:
    """Run a shell command and return (success, combined_output).

    Args:
        command: Shell command string to execute.
        cwd: Working directory for the command.

    Returns:
        Tuple of (success: bool, output: str).
    """
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, cwd=cwd
    )
    combined = result.stdout + result.stderr
    return result.returncode == 0, combined


async def handle_task(websocket, config):
    """Handle a single task lifecycle with the Chrome Extension."""
    repo_path = Path(config["repo_path"]).expanduser().resolve()
    sync_path = Path(config["sync_path"]).expanduser().resolve()
    download_path = Path(config["download_path"]).expanduser().resolve()

    # Step 1: Zip the repo initially for the session
    print("[CLI] Initializing session... Zipping repository using git archive...")
    zip_output = sync_path / "workspace.zip"
    await asyncio.to_thread(zip_repo, repo_path, zip_output)
    print(f"[CLI] Repo zipped to {zip_output}")

    while True:
        # Step 2: Wait for user prompt input
        prompt = await asyncio.to_thread(input, "[CLI] Enter task prompt (or type /zip to re-zip, /exit to quit): ")
        prompt = prompt.strip()
        
        if prompt.lower() == "/exit":
            print("[CLI] Exiting session.")
            break
        elif prompt.lower() == "/zip":
            print("[CLI] Re-zipping repository using git archive...")
            await asyncio.to_thread(zip_repo, repo_path, zip_output)
            print(f"[CLI] Repo re-zipped to {zip_output}")
            continue

        if not prompt:
            prompt = "Review the codebase and fix any bugs you find."

        model = await asyncio.to_thread(input, f"[CLI] Enter model name (default: {config['default_model']}): ")
        model = model.strip()
        if not model:
            model = config["default_model"]

        # Step 3: Send START_TASK to Extension
        payload = {
            "action": "START_TASK",
            "onedrive_link": config["onedrive_link"],
            "model": model,
            "prompt": prompt,
            "system_instruction": (
                "Bạn là AI Software Engineer. Hãy đọc file mã nguồn tại link OneDrive sau, "
                "thực hiện yêu cầu, và xuất kết quả ra file zip tên output.zip kèm nút Download."
            ),
        }
        try:
            await websocket.send(json.dumps(payload))
            print("[CLI] Task sent to Extension. Waiting for Copilot to process...")
        except websockets.exceptions.ConnectionClosed:
            print("[CLI] WebSocket connection closed before task could be sent.")
            return

        # Step 4: Listen for status updates and completion for this task
        while True:
            try:
                message = await websocket.recv()
            except websockets.exceptions.ConnectionClosed:
                print("[CLI] WebSocket disconnected during task execution.")
                return

            data = json.loads(message)
            event = data.get("event", "")
            status = data.get("status", "")

            if event == "STATUS_UPDATE":
                print(f"[CLI] Status: {status} — {data.get('message', '')}")

            elif event == "TASK_COMPLETE" and status == "FILE_DOWNLOADED":
                filepath = data.get("filepath", "")
                if filepath and Path(filepath).exists():
                    zip_file = Path(filepath)
                else:
                    filename = data.get("filename", "output.zip")
                    zip_file = download_path / filename

                print(f"[CLI] File downloaded: {zip_file}. Applying changes...")

                if extract_zip(zip_file, repo_path):
                    print("[CLI] Changes applied to repo.")
                    success, output = run_verify(config["verify_command"], repo_path)
                    if success:
                        print("[CLI] ✅ Verification PASSED!")
                        # Show git diff
                        _, diff = run_verify("git diff", repo_path)
                        if diff.strip():
                            print(f"[CLI] Changes:\n{diff}")
                    else:
                        print(f"[CLI] ❌ Verification FAILED:\n{output}")
                else:
                    print("[CLI] ❌ Failed to extract downloaded file.")
                
                break # Task finished, go back to ask for next prompt

            elif event == "ERROR":
                print(f"[CLI] ❌ Error at step '{data.get('step', '?')}': {data.get('message', '')}")
                break # Task finished with error, go back to ask for next prompt

async def safe_handle_task(websocket, config):
    try:
        await handle_task(websocket, config)
    except websockets.exceptions.ConnectionClosed:
        print("[CLI] WebSocket disconnected during task execution.")
    except Exception as e:
        print(f"[CLI] Unexpected error in task: {e}")


async def main():
    """Start WebSocket server and wait for Extension to connect."""
    config = load_config()
    download_path = Path(config["download_path"]).expanduser()
    download_path.mkdir(parents=True, exist_ok=True)

    port = config["websocket_port"]
    print(f"[CLI] Starting WebSocket server on ws://localhost:{port}")
    print("[CLI] Waiting for Chrome Extension to connect...")

    async with websockets.serve(
        lambda ws: safe_handle_task(ws, config), "0.0.0.0", port
    ):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    asyncio.run(main())
