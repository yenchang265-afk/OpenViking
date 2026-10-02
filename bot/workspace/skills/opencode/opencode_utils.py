#!/usr/bin/env python3
"""Simple test for opencode-ai SDK"""

import json
import os
import subprocess
import sys
import time
import traceback

from opencode_ai import Opencode


def execute_cmd(cmd):
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            text=True,
            encoding="utf-8",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # 捕獲錯誤輸出
            check=True,  # 等價於check_output的行為，命令失敗會拋異常
        )
        stdout = result.stdout.strip()  # 去除空白符（換行/空格）
        return stdout
    except subprocess.CalledProcessError as e:
        # 捕獲命令執行失敗的異常（返回碼非0）
        print(f"命令執行失敗：{e}")
        return None
    except Exception as e:
        # 捕獲其他異常（如命令不存在、超時等）
        print(f"執行異常：{str(e)}")
        return None


def start_opencode():
    """子程序函式：啟動opencode serve並完全脫離子程序控制"""
    pid = None
    try:
        if sys.platform == "win32":
            # Windows：使用CREATE_NEW_PROCESS_GROUP建立獨立程序組，detach脫離父程序
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
            proc = subprocess.Popen(
                ["opencode", "serve"],
                shell=False,
                creationflags=creationflags,
                stdout=subprocess.DEVNULL,  # 重定向輸出避免控制台關聯
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            pid = proc.pid
        else:
            # Linux/macOS：使用os.setsid建立新會話，完全脫離控制終端
            # 先fork一次，再啟動程序，確保脫離所有父程序關聯
            cmd = ["opencode", "serve"]
            # 建立新會話 + 重定向所有輸出
            with open("opencode.log", "a", encoding="utf-8") as log_file:
                proc = subprocess.Popen(
                    cmd,
                    preexec_fn=os.setsid,  # 關鍵：建立新的會話ID
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                )
                pid = proc.pid

        print(f"opencode serve已啟動，PID: {pid}")
        # 短暫等待確保程序啟動成功
        time.sleep(2)
        return pid
    except Exception as e:
        print(f"啟動opencode失敗: {e}")
        traceback.print_exc()
        return None


def check_serve_status():
    """測試opencode連線，失敗則啟動服務並重試"""
    try:
        client = Opencode(base_url="http://127.0.0.1:4096")
        client.app.modes()
    except Exception as e:
        print(f"連線opencode失敗，錯誤: {e}")
        # 啟動服務
        pid = start_opencode()
        if pid:
            # 啟動後重試連線
            time.sleep(3)


def read_new_messages(client, session_id, last_ts):
    """
    讀取上一次之後的訊息， 通過client.session.messages實現，注意
    """
    messages = client.session.messages(id=session_id, extra_query={"limit": 10})
    next_ts = last_ts
    new_messages = []
    has_finished = False

    for message in messages:
        created_time = 0
        if hasattr(message, "info") and message.info:
            if hasattr(message.info, "time") and message.info.time:
                if hasattr(message.info.time, "created"):
                    created_time = message.info.time.created

        if created_time > last_ts:
            new_messages.append(message)
            if created_time > next_ts:
                next_ts = created_time

    if messages:
        last_message = messages[-1]
        if last_message.parts:
            for part in last_message.parts:
                if hasattr(part, "type") and part.type == "step-finish":
                    has_finished = True

    status = "finished" if has_finished else "running"
    return status, new_messages, next_ts


file_path = "status.json"


def read_status():
    # 檢查檔案是否存在
    if not os.path.exists(file_path):
        return {}
    # 讀取並解析JSON檔案
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception as e:
        # 捕獲其他未知異常
        print(f"讀取 {file_path} 時發生錯誤：{e}")
        return {}


def write_status(status):
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(status))
    except Exception as e:
        # 捕獲其他未知異常
        print(f"寫入 {file_path} 時發生錯誤：{e}")


def list_project(client):
    import httpx

    http_client = httpx.Client(base_url="http://127.0.0.1:4096")
    response = http_client.get("/project")
    projects = response.json()
    project_list = []
    for p in projects:
        project_list.append({"id": p.get("id"), "path": p.get("worktree")})
    return project_list
