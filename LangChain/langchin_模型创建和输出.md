 ## invoke 返回内容

```python
AIMessage(
    # --- 核心内容 ---
    content='2 + 3 * 2 = **8**',  # 模型生成的最终文本答案
    additional_kwargs={
        'refusal': None  # 模型拒绝回答的情况（如触碰安全策略），None 表示正常回答
    },
    
    # --- 响应元数据（API 返回的详细原始数据） ---
    response_metadata={
        'token_usage': {
            'completion_tokens': 15,     # 生成回答消耗的 Token 数（输出）
            'prompt_tokens': 16,         # 用户输入消耗的 Token 数（输入）
            'total_tokens': 31,          # 本次交互总共消耗的 Token
            'completion_tokens_details': {
                'accepted_prediction_tokens': 0, # 预测性生成的 Token 数
                'audio_tokens': 0,               # 音频生成消耗（如有）
                'reasoning_tokens': 0,           # 推理模型（如 o1）思考过程消耗的 Token
                'rejected_prediction_tokens': 0  # 被拒绝的预测 Token
            },
            'prompt_tokens_details': {
                'audio_tokens': 0,   # 输入中的音频 Token 数
                'cached_tokens': 0   # 命中的缓存 Token 数（能省钱/提速）
            }
        },
        
        # --- 延迟性能监控（单位：毫秒 ms） ---
        'latency_checkpoint': {
            'engine_tbt_ms': 4,           # 引擎 Token 间平均间隔时间
            'engine_ttft_ms': 36,         # 引擎生成首个 Token 的时间
            'engine_ttlt_ms': 100,        # 引擎生成最后一个 Token 的时间
            'pre_inference_ms': 86,       # 推理前的预处理耗时（安全审核、Token 化等预处理）
            'service_tbt_ms': 4,          # 服务端token与token之间生成的间隔时间，决定了打字机效果是否丝滑
            'service_ttft_ms': 280,       # 服务端接收到请求到输出首字的总时间
            'service_ttlt_ms': 338,       # 服务端完成全部输出的总时间
            'total_duration_ms': 259,     # 本次请求在系统中记录的总时长
            'user_visible_ttft_ms': 194   # 用户看到第一个字跳出来等待的时间
        },
        
        'model_provider': 'openai',                        # 模型供应商
        'model_name': 'gpt-5.4-mini-2026-03-17',           # 使用的具体模型版本
        'system_fingerprint': None,                        # 系统指纹，用于追踪模型后端的配置变更
        'id': 'chatcmpl-DgWob...',                         # API层面的响应 ID
        'service_tier': 'default',                         # 服务层级（如按量付费或订阅）
        'finish_reason': 'stop',                           # 停止原因：stop（自然结束）、length（长度受限）
        'logprobs': None                                   # 对数概率（通常用于分析词汇选择的可能性）
    },
    
    # --- LangChain 内部标识 ---
    id='lc_run--019e3659-...',  # LangChain 追踪此条运行的唯一 ID
    
    # --- 工具调用信息 ---
    tool_calls=[],              # 正常触发的外部工具调用列表
    invalid_tool_calls=[],      # 触发失败或格式错误的工具调用
    
    # --- 统一消耗元数据（LangChain 标准化后的消耗格式） ---
    usage_metadata={
        'input_tokens': 16,     # 输入 Token 数
        'output_tokens': 15,    # 输出 Token 数
        'total_tokens': 31,     # 总 Token 数
        'input_token_details': {
            'audio': 0,
            'cache_read': 0     # 从缓存中读取的输入数量
        },
        'output_token_details': {
            'audio': 0,
            'reasoning': 0      # 包含在输出中的推理 Token
        }
    }
)
```

