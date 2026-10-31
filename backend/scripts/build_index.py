#!/usr/bin/env python3
"""构建向量索引 — 从 sample_clauses.json 加载数据，写入 Milvus 集合。

需先启动 Milvus：docker compose --profile milvus up -d（仓库根目录）。
"""

import json
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from config import settings
from vector.embeddings import create_embedding_model
from vector.milvus_store import MilvusStore


def main():
    data_file = PROJECT_ROOT / "data" / "sample_clauses.json"

    if not data_file.exists():
        print(f"错误：数据文件不存在: {data_file}")
        sys.exit(1)

    with open(data_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    clauses = data["clauses"]
    print(f"加载了 {len(clauses)} 条示例条款")

    texts = [f"{c['title']}：{c['content']}" for c in clauses]
    metadata = [
        {"id": c["id"], "title": c["title"], "category": c["category"], "source": c["source"]}
        for c in clauses
    ]

    print("正在加载 Embedding 模型...")
    model = create_embedding_model()

    print(f"正在嵌入并写入 Milvus 集合 {settings.MILVUS_COLLECTION}（插入即持久化）...")
    store = MilvusStore(embedding_model=model)
    store.add(texts=texts, metadata=metadata)

    print(f"完成！共 {store.size} 条记录")


if __name__ == "__main__":
    main()
