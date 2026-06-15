-- 创建pgvector扩展
CREATE EXTENSION IF NOT EXISTS vector;

-- 创建知识库向量表
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding vector(512),
    source TEXT NOT NULL,
    category TEXT,
    chunk_index INTEGER,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 创建向量索引（使用IVFFlat）
CREATE INDEX IF NOT EXISTS knowledge_embedding_idx 
ON knowledge_chunks 
USING ivfflat (embedding vector_cosine_ops) 
WITH (lists = 100);

-- 创建全文搜索索引
CREATE INDEX IF NOT EXISTS knowledge_source_idx ON knowledge_chunks(source);
CREATE INDEX IF NOT EXISTS knowledge_category_idx ON knowledge_chunks(category);