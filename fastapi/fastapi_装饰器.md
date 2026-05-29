---
last_modified: 2026-05-29 17:18
---

# FastAPI 装饰器

FastAPI 装饰器用于把 Python 函数注册为路由、生命周期处理器或中间件。装饰器先声明匹配规则和配置，函数再实现具体业务逻辑。

## 1. `app.get`

`app.get(path)` 注册一个处理 HTTP `GET` 请求的路由。`GET` 通常用于查询资源，不应通过请求体修改服务器状态。

```python
@app.get("/users/{user_id}", response_model=User)
async def get_user(user_id: int):
    return find_user(user_id)
```

常用参数包括 `response_model`、`status_code`、`tags`、`summary`、`description`、`dependencies` 和 `responses`。例如，`response_model` 可以约束返回结构并生成 OpenAPI 文档。

## 2. `app.post`

`app.post(path)` 注册一个处理 HTTP `POST` 请求的路由。`POST` 常用于创建资源或提交需要处理的数据，请求体一般使用 Pydantic 模型声明。

```python
class UserCreate(BaseModel):
    username: str
    password: str


@app.post("/users", response_model=User, status_code=201)
async def create_user(user: UserCreate):
    return save_user(user)
```

`status_code=201` 表示创建成功。FastAPI 会读取 JSON 请求体并根据 `UserCreate` 自动校验类型和字段。

## 3. `app.on_event`

`app.on_event("startup")` 和 `app.on_event("shutdown")` 用于注册应用启动和关闭时执行的函数，常见用途包括初始化连接池、加载模型和释放资源。

```python
@app.on_event("startup")
async def startup():
    await database.connect()


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
```

在当前 FastAPI 版本中，`on_event` 已被标记为弃用方向，新项目推荐使用 `lifespan` 管理启动和关闭逻辑：

```python
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await database.connect()
    yield
    await database.disconnect()


app = FastAPI(lifespan=lifespan)
```

## 4. `app.middleware`

`@app.middleware("http")` 注册 HTTP 中间件。中间件包裹请求处理过程，可以在请求进入路由前和响应返回后执行逻辑，适合日志、耗时统计、通用响应头和跨域等横切功能。

```python
@app.middleware("http")
async def add_process_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(time.perf_counter() - start)
    return response
```

`call_next(request)` 会把请求交给后续中间件和路由；中间件必须返回响应对象。

## 5. 其他常用装饰器

### 5.1 其他 HTTP 方法路由

FastAPI 为不同 HTTP 方法提供对应装饰器：

```python
@app.put("/users/{user_id}")
async def update_user(user_id: int, user: UserCreate):
    ...


@app.patch("/users/{user_id}")
async def patch_user(user_id: int, user: UserCreate):
    ...


@app.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: int):
    ...


@app.options("/users")
async def options_users():
    ...
```

`put` 通常表示整体更新，`patch` 表示部分更新，`delete` 删除资源。也可以使用 `app.api_route()` 同时声明多个 HTTP 方法。

### 5.2 路由级依赖：`dependencies`

在路由装饰器中声明依赖时，依赖会执行，但返回值不会注入路由函数，适合鉴权等只需要校验的逻辑：

```python
@app.get("/admin", dependencies=[Depends(require_token)])
async def admin_page():
    return {"ok": True}
```

### 5.3 异常处理器：`app.exception_handler`

`@app.exception_handler(ExceptionType)` 为指定异常注册统一处理函数，适合统一错误响应格式和记录异常日志：

```python
@app.exception_handler(MyException)
async def handle_my_exception(request: Request, exc: MyException):
    return JSONResponse(status_code=400, content={"detail": str(exc)})
```

### 5.4 路由分组：`router.get` 等

使用 `APIRouter` 拆分模块时，路由装饰器写在 `router` 上，再通过 `app.include_router(router)` 挂载：

```python
router = APIRouter(prefix="/users", tags=["users"])


@router.get("/{user_id}")
async def get_user(user_id: int):
    ...
```

## 6. 选择建议

| 装饰器 | 主要作用 | 典型场景 |
| --- | --- | --- |
| `app.get` | 查询资源 | 获取列表、详情 |
| `app.post` | 创建或提交数据 | 注册、创建订单 |
| `app.on_event` / `lifespan` | 管理应用生命周期 | 初始化和释放资源 |
| `app.middleware` | 包裹请求和响应 | 日志、计时、响应头 |
| `app.exception_handler` | 统一异常处理 | 自定义错误响应 |
| `router.get` 等 | 模块化路由 | 按业务拆分 API |

## 7. 官方文档

- [FastAPI 路径操作装饰器](https://fastapi.tiangolo.com/tutorial/path-operation-configuration/)
- [FastAPI 请求方法与路径操作](https://fastapi.tiangolo.com/tutorial/first-steps/)
- [FastAPI 应用事件（旧方式）](https://fastapi.tiangolo.com/advanced/events/)
- [FastAPI Lifespan 事件](https://fastapi.tiangolo.com/advanced/events/#lifespan)
- [FastAPI 中间件](https://fastapi.tiangolo.com/tutorial/middleware/)
- [FastAPI 处理错误](https://fastapi.tiangolo.com/tutorial/handling-errors/)
- [FastAPI APIRouter](https://fastapi.tiangolo.com/tutorial/bigger-applications/)
