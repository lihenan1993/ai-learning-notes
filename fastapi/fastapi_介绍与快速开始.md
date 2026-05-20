---
last_modified: 2026-05-20 16:20
---

# FastAPI 介绍与快速开始

## 1. FastAPI 是什么

FastAPI 是一个用于构建 Python Web API 的现代框架。它基于 Python 类型注解定义请求参数和数据结构，并使用 ASGI（异步服务器网关接口）规范运行。

## 2. FastAPI 的优点

- **开发效率高**：类型注解让接口参数、请求体和返回值更清楚，编辑器也能提供补全和静态检查。
- **自动校验与转换**：根据声明的数据类型解析、转换和校验输入；校验失败时会返回结构化错误信息。
- **自动生成 API 文档**：集成 OpenAPI，启动服务后可以通过 `/docs` 打开 Swagger UI，也可以通过 `/redoc` 查看 ReDoc 文档。
- **支持异步**：可以使用 `async def` 编写异步接口，并运行在 ASGI 服务器上；同步函数也可以使用。
- **性能良好**：建立在 Starlette、Pydantic 等成熟组件之上，适合构建高性能 API 服务。
- **标准兼容**：自动生成符合 OpenAPI 和 JSON Schema 规范的接口描述，便于工具集成。

## 3. 使用 uv 管理项目

`uv` 是 Python 项目与依赖管理工具。它可以创建虚拟环境、安装依赖、维护锁定文件，并通过 `uv run` 在项目环境中运行命令。

本练习项目位于 `fastapitest/`，项目配置已声明 Python 版本和依赖。进入项目目录后，可以用下面的命令添加依赖：

```powershell
cd fastapitest
uv add fastapi
uv add uvicorn
```

`uv add` 会把依赖写入 `pyproject.toml`，并更新 `uv.lock`。新环境中可运行 `uv sync`，按项目配置安装依赖。

## 4. ASGI 是什么

ASGI（Asynchronous Server Gateway Interface，异步服务器网关接口）是 Python Web 服务器与 Web 应用之间的一套接口规范。它规定服务器如何把 HTTP 请求、连接信息等交给应用，以及应用如何把响应或后续消息返回给服务器。

ASGI 的设计支持异步通信，因此除了普通 HTTP 请求，也能处理 WebSocket 等需要保持连接的场景。它是接口标准，不是具体的 Web 框架或服务器：FastAPI 实现 ASGI 应用接口，Uvicorn 实现 ASGI 服务器接口。请求大致按这个方向流动：

```text
浏览器 → Uvicorn（ASGI 服务器）→ FastAPI（ASGI 应用）→ Uvicorn → 浏览器
```

有了 ASGI 这样的共同约定，符合规范的服务器可以运行符合规范的应用，应用也不必绑定到某一个特定服务器。

## 5. Uvicorn 是什么

Uvicorn 是一个轻量、快速的 ASGI 服务器，负责启动 Python Web 应用、监听网络端口，并把收到的 HTTP 请求交给应用处理，再将响应返回给客户端。FastAPI 是编写 API 应用的框架；Uvicorn 是运行这个应用的服务器。可以把 FastAPI 看作定义“请求如何处理”，把 Uvicorn 看作负责“接收和传递请求”。

Uvicorn 支持 ASGI，因此可以运行 FastAPI、Starlette 等 ASGI 应用。它也支持异步 I/O，适合承载使用 `async def` 编写的接口。

常见启动命令如下：

```powershell
uv run uvicorn main:app --reload
```

- `main:app`：从 `main.py` 导入名为 `app` 的应用对象。
- `--reload`：开发时监视代码变化并自动重启服务。
- 默认监听 `127.0.0.1:8000`；可以用 `--host` 和 `--port` 修改，例如 `--host 0.0.0.0 --port 8080`。

`--reload` 适合本地开发，不用于生产部署。运行 `uv run main.py` 时，仍然是 Uvicorn 在提供服务，只是由 Python 文件里的 `uvicorn.run(...)` 启动和配置它。

## 6. 编写最小应用

在项目根目录创建 `main.py`：

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def read_root():
    return {"message": "Hello, World!"}
```

这里创建了 FastAPI 应用对象 `app`，并声明了一个处理 `GET /` 请求的异步函数。FastAPI 会将返回的 Python 字典编码为 JSON 响应。

## 7. 启动服务的两种方式

### 方式一：直接运行 Uvicorn 命令

```powershell
uv run uvicorn main:app --reload
```

`main:app` 表示从 `main.py` 模块导入名为 `app` 的 ASGI 应用对象。`--reload` 会在开发时监视源文件变化并自动重启服务，不建议在生产环境使用。

### 方式二：运行 Python 文件

如果 `main.py` 中包含 `if __name__ == "__main__":`，并在其中调用 `uvicorn.run(...)`，可以这样启动：

```powershell
uv run main.py
```

例如：

```python
import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
async def read_root():
    return {"message": "Hello, World!"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
```

第一种方式把 Uvicorn 参数放在命令行里，适合直接启用 `--reload` 等开发选项；第二种方式从 Python 入口启动，服务器配置写在代码中。练习项目可以按当前 `main.py` 使用任一方式。

## 8. 验证运行结果

服务启动后，默认可在浏览器访问：

- `http://127.0.0.1:8000/`：查看 JSON 响应。
- `http://127.0.0.1:8000/docs`（也可以写作 `127.0.0.1:8000/docs`）：打开可交互的 Swagger API 文档。
- `http://127.0.0.1:8000/redoc`：ReDoc API 文档。

停止服务时，在运行命令的终端按 `Ctrl+C`。

