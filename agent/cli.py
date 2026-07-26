import asyncio
import re
import zipfile
from pathlib import Path
import websockets

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.history import FileHistory

from agent.config import load_config, AgentState
from agent.runner import TaskRunner
from agent.repo import zip_repo, apply_downloaded_zip, run_verify
from agent.ui import (
    console, print_sys, print_user_msg, print_applied, print_verify, print_help,
    make_toolbar, print_header_and_pad, TOOLBAR_STYLE, Panel
)

async def main_loop():
    config = load_config()

    download_path = Path(config["download_path"]).expanduser()
    download_path.mkdir(parents=True, exist_ok=True)

    state_file = Path(config.get("session_state_file", "./.copilot-agent-state.json")).expanduser()
    state = AgentState(state_file)

    runner = TaskRunner(config, state)
    repo_path = Path(config["repo_path"]).expanduser().resolve()
    sync_path = Path(config["sync_path"]).expanduser().resolve()
    max_retry = config.get("max_retry_on_failure", 1)
    sync_command = config.get("sync_command")
    sync_delay = config.get("sync_delay", 0)

    port = config["websocket_port"]
    server = await websockets.serve(runner.handle_connection, "0.0.0.0", port)
    print_sys(f"WebSocket server on ws://localhost:{port} — waiting for extension…", "dim")

    print_sys("Zipping repository…", "dim")
    repo_name = repo_path.name
    zip_filename = f"{repo_name}.zip"
    zip_output = sync_path / zip_filename
    await asyncio.to_thread(zip_repo, repo_path, zip_output, sync_command, sync_delay)
    print_sys(f"✓ Zipped → {zip_output}", "green")

    history_path = Path("~/.copilot-agent-history").expanduser()
    prompt_session = PromptSession(history=FileHistory(str(history_path)))

    current_model = state.model or config["default_model"]
    is_new_session = True
    output_mode = False

    console.clear()
    print_header_and_pad(runner.connected, current_model, output_mode)

    while True:
        try:
            with patch_stdout(raw=True):
                raw: str = await prompt_session.prompt_async(
                    "❯ ",
                    bottom_toolbar=make_toolbar(
                        state.last_session_id, runner.connected,
                        current_model, output_mode
                    ),
                    style=TOOLBAR_STYLE,
                )
        except (EOFError, KeyboardInterrupt):
            print_sys("\nGoodbye!", "dim")
            if state.last_session_id:
                print_sys(f"💡 Để tiếp tục session này lần sau, gõ: /resume {state.last_session_id}", "dim cyan")
            break

        cmd = raw.strip()
        if not cmd:
            continue
            
        print("\033[F\033[K", end="")

        if cmd.lower() == "/exit":
            print_sys("Goodbye!", "dim")
            if state.last_session_id:
                print_sys(f"💡 Để tiếp tục session này lần sau, gõ: /resume {state.last_session_id}", "dim cyan")
            break

        if cmd.lower() == "/help":
            print_help()
            continue

        if cmd.lower() == "/zip":
            print_sys("Re-zipping…", "dim")
            await asyncio.to_thread(zip_repo, repo_path, zip_output, sync_command, sync_delay)
            print_sys(f"✓ Re-zipped → {zip_output}", "green")
            continue

        if cmd.lower() == "/diff":
            _, diff = await asyncio.to_thread(run_verify, "git diff", repo_path)
            if diff.strip():
                console.print(Panel(diff, title="git diff", border_style="yellow"))
            else:
                print_sys("No changes in working tree.", "dim")
            continue

        if cmd.lower() == "/verify":
            print_sys(f"Running: {config['verify_command']}", "dim")
            success, output = await asyncio.to_thread(
                run_verify, config["verify_command"], repo_path
            )
            print_verify(success, output)
            continue

        if cmd.lower().startswith("/skill"):
            parts = cmd.split()
            if len(parts) > 1 and parts[1] == "list":
                skills_dir = Path(config.get("skills_dir", "./skills")).expanduser().resolve()
                if skills_dir.exists():
                    skills = sorted(
                        d.name for d in skills_dir.iterdir()
                        if d.is_dir() and (d / "skills.md").exists()
                    )
                    print_sys(f"Available skills: {', '.join(skills) or 'none'}", "cyan")
                else:
                    print_sys(f"Skills directory not found: {skills_dir}", "yellow")
            continue

        if cmd.lower().startswith("/resume"):
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                given_id = parts[1].strip()
                state.last_session_id = given_id
                state.save()
                is_new_session = False
                console.print(f"Session set to: [cyan]{given_id}[/cyan] — next prompt will resume this conversation.")
            elif state.last_session_id:
                is_new_session = False
                console.print(f"Will resume session: [cyan]{state.last_session_id}[/cyan]")
            else:
                print_sys("No saved session. Provide ID: /resume <uuid>", "yellow")
            continue

        if cmd.lower() == "/out":
            output_mode = not output_mode
            state_str = "[green]ON[/green]" if output_mode else "[dim]OFF[/dim]"
            console.print(f"Output rules template: {state_str} "
                          "(sẽ đính kèm vào prompt tiếp theo nếu ON)")
            continue

        if cmd.lower().startswith("/model"):
            parts = cmd.split(maxsplit=2)
            if len(parts) > 1:
                current_model = parts[1].strip()
            else:
                models = list({"auto", "quick", "think", "sonnet", "opus", "gpt5.5", "gpt5.6", "gpt"})
                console.print(f"Available models: [dim]{' · '.join(sorted(models))}[/dim]")
                try:
                    mi = await prompt_session.prompt_async(
                        f"Model [{current_model}]: "
                    )
                    current_model = mi.strip() or current_model
                except (EOFError, KeyboardInterrupt):
                    continue
                console.print(f"[dim cyan]Model switched to: {current_model}[/dim cyan]")
            
            state.model = current_model
            state.save()
            
            if len(parts) > 2:
                cmd = parts[2].strip()
            else:
                continue

        if cmd.lower().startswith("/new"):
            is_new_session = True
            parts = cmd.split(maxsplit=2)
            if len(parts) > 1:
                current_model = parts[1].strip()
            else:
                try:
                    mi = await prompt_session.prompt_async(
                        f"Model [{config['default_model']}]: "
                    )
                    current_model = mi.strip() or config["default_model"]
                except (EOFError, KeyboardInterrupt):
                    current_model = config["default_model"]
            state.model = current_model
            state.save()
            console.clear()
            print_header_and_pad(runner.connected, current_model, output_mode)
            
            if len(parts) > 2:
                cmd = parts[2].strip()
            else:
                continue

        inline_out = bool(re.search(r'(?:^|\s)/out(?:\s|$)', cmd))
        clean_cmd = re.sub(r'\s*/out\b', '', cmd).strip()
        request_output = output_mode or inline_out

        print_user_msg(clean_cmd)
        result = await runner.send_task(clean_cmd, is_new_session, current_model,
                                        request_output=request_output)
        is_new_session = False 

        if result is None:
            continue

        if result["type"] == "error":
            continue

        if result["type"] != "file":
            continue

        zip_file: Path = result["path"]
        if not zip_file.exists():
            print_sys(f"❌ Downloaded file not found: {zip_file}", "red")
            print_sys("Copilot response was shown above. No file to apply.", "dim")
            continue

        try:
            header = zip_file.read_bytes()[:4]
            if header != b'PK\x03\x04':
                print_sys(f"❌ File is not a valid zip (got: {header!r}). Skipping apply.", "red")
                zip_file.unlink(missing_ok=True)
                continue
        except OSError as e:
            print_sys(f"❌ Cannot read file: {e}", "red")
            continue

        try:
            applied = await asyncio.to_thread(apply_downloaded_zip, zip_file, repo_path)
        except zipfile.BadZipFile as e:
            print_sys(f"❌ Bad zip file: {e}", "red")
            zip_file.unlink(missing_ok=True)
            continue

        if not applied:
            print_sys("⚠ No files in zip to apply.", "yellow")
            continue

        print_sys(f"✓ Applied {len(applied)} file(s):", "green")
        print_applied(applied)

        retry_left = max_retry
        while True:
            print_sys(f"Running verify: {config['verify_command']}", "dim")
            success, output = await asyncio.to_thread(
                run_verify, config["verify_command"], repo_path
            )
            print_verify(success, output)

            if success or retry_left <= 0:
                break

            retry_left -= 1
            print_sys(f"Auto-retrying with error context ({retry_left} retries left)…", "yellow")
            retry_prompt = (
                f"Verify thất bại với lỗi sau:\n\n{output[:3000]}\n\n"
                "Hãy phân tích lỗi và sửa lại."
            )
            r2 = await runner.send_task(retry_prompt, False, current_model,
                                        request_output=output_mode)
            if r2 is None or r2["type"] != "file":
                break
            zip2: Path = r2["path"]
            if not zip2.exists():
                break
            applied2 = await asyncio.to_thread(apply_downloaded_zip, zip2, repo_path)
            if applied2:
                print_sys(f"✓ Retry applied {len(applied2)} file(s)", "green")
                print_applied(applied2)

    server.close()
    try:
        await asyncio.wait_for(server.wait_closed(), timeout=2.0)
    except asyncio.TimeoutError:
        pass 
