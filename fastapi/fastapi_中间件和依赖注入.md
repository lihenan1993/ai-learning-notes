---
last_modified: 2026-05-31 17:10
---

# FastAPI 中间件和依赖注入

## 1. 中间件

![中间件与依赖注入](fastapi配图_中间件和依赖注入.png)

### 1.1 定义

中间件（Middleware）位于客户端请求与 FastAPI 路由处理之间。它可以在请求到达路由之前执行逻辑，也可以在路由生成响应之后修改或检查响应。中间件通常作用于应用中的所有请求，因此适合处理请求日志、计时、跨域、通用响应头等横切逻辑。

执行过程可以概括为：

```text
请求 → 中间件（进入阶段）→ 路由处理 → 中间件（返回阶段）→ 响应
```

### 1.2 使用 `@app.middleware("http")`

FastAPI 的 HTTP 中间件函数接收 `request` 和 `call_next`。调用并等待 `call_next(request)` 会把请求交给后续中间件和路由；拿到响应后，可以继续处理并返回它。

```python
import time
from fastapi import FastAPI, Request

app = FastAPI()


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start
    response.headers["X-Process-Time"] = str(elapsed)
    return response
```

在 `call_next` 前后分别是请求进入和响应返回阶段。中间件必须把响应返回给客户端；需要在响应头中增加处理时长时，可以在 `call_next` 后修改响应。

### 1.3 多个中间件的执行顺序

多个中间件会形成嵌套调用：请求阶段逐层进入，响应阶段按相反方向返回。`middleware.py` 中通过两个计时中间件的 `Start` 和 `End` 日志演示了这种栈式行为。多个中间件的实际先后顺序取决于它们的注册顺序；阅读日志时可以观察请求进入与响应返回的嵌套关系。

## 2. 依赖注入

### 2.1 定义

依赖注入（Dependency Injection，DI）是将路由处理所需的值或功能交给框架提供，而不是在路由函数中自行创建所有依赖。FastAPI 使用 `Depends` 声明依赖，框架会在调用路由前解析依赖，并把结果传给路由函数。

依赖可以用来复用身份验证、数据库会话、分页参数、配置读取等逻辑。依赖函数也可以继续声明其他依赖。

### 2.2 将依赖结果注入路由

```python
from fastapi import Depends


async def get_current_user():
    return {"username": "alice"}


@app.get("/profile")
async def profile(user=Depends(get_current_user)):
    return {"user": user}
```

请求 `/profile` 时，FastAPI 先调用 `get_current_user`，再把返回值作为 `user` 参数传给 `profile`。

### 2.3 只执行依赖，不接收其返回值

如果只需要依赖执行时的校验逻辑，不需要在路由函数中使用依赖返回值，可以放到装饰器的 `dependencies` 列表：

```python
from fastapi import Depends, HTTPException, Request


async def require_token(request: Request):
    if request.headers.get("x-token") != "secret":
        raise HTTPException(status_code=401, detail="令牌无效")


@app.get("/slow", dependencies=[Depends(require_token)])
async def slow():
    return {"ok": True}
```

这正是 `middleware.py` 中 `/slow` 路由使用的方式。没有正确的 `x-token: secret` 请求头时，依赖抛出 `HTTPException`，路由函数不会执行。

### 2.4 装饰器依赖与函数形参依赖的区别

两种写法都会执行依赖，也都会触发依赖内部的校验和异常处理；区别在于路由函数是否需要依赖的返回值。

**函数形参写法：需要使用依赖返回值时使用。** FastAPI 会把依赖结果放进 `commons` 参数：

```python
from fastapi import Depends, Query


async def common_parameters(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=60),
):
    return {"skip": skip, "limit": limit}


@app.get("/news/news_list")
async def get_news_list(commons=Depends(common_parameters)):
    return commons
```

调用 `/news/news_list?skip=20&limit=5` 时，`commons` 是 `{"skip": 20, "limit": 5}`。

**装饰器 `dependencies` 写法：只需要依赖产生副作用或校验时使用。** 依赖仍会执行，但返回值不会传给路由函数：

```python
@app.get("/news/news_list", dependencies=[Depends(common_parameters)])
async def get_news_list():
    return {"message": "分页参数已校验，但路由函数不读取依赖结果"}
```

因此，如果分页函数返回的 `skip` 和 `limit` 要用于查询或响应，应采用函数形参写法；如果依赖只负责令牌检查等工作，可以使用装饰器写法。装饰器方式不会让依赖“只校验不解析参数”：依赖中的查询参数仍会被解析和校验，只是其返回值被丢弃。

### 2.5 依赖的作用范围

- **单个路由**：在函数参数中用 `Depends(...)`，或在路由装饰器的 `dependencies` 参数中声明。
- **一组路由**：在 `APIRouter` 上声明共同依赖。
- **整个应用**：在 `FastAPI(dependencies=[...])` 中声明应用级依赖。

## 3. 中间件和依赖注入如何选择

| 机制 | 主要范围 | 常见用途 |
| --- | --- | --- |
| 中间件 | 经过应用中间件栈的请求 | 通用日志、计时、响应头、跨域处理 |
| 依赖注入 | 显式声明该依赖的路由或路由组 | 令牌校验、当前用户、数据库会话、业务参数复用 |

需要对请求和响应做通用处理时通常使用中间件；需要把可复用结果或业务校验提供给特定路由时通常使用依赖注入。

## 4. 当前练习文件

示例代码位于 `fastapitest/middleware.py`，可以这样启动：

```powershell
cd fastapitest
uv run uvicorn middleware:app --reload
```

- 访问 `/`，观察两个中间件输出的进入和返回日志。
- 访问 `/slow` 并附带请求头 `x-token: secret`，可以得到成功响应；缺少或令牌错误时会收到 `401`。

## 5. 官方文档

- [FastAPI 中间件](https://fastapi.tiangolo.com/tutorial/middleware/)
- [FastAPI 依赖注入](https://fastapi.tiangolo.com/tutorial/dependencies/)
- [FastAPI 将依赖添加到路由装饰器](https://fastapi.tiangolo.com/tutorial/dependencies/dependencies-in-path-operation-decorators/)
