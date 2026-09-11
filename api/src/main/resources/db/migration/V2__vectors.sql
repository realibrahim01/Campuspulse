-- CampusPulse — V2 vector layer (FAISS-fallback form).
--
-- DECISION LOG (9 Sep 2026): pgvector is not available on this native Windows
-- Postgres 18 install (the standard EDB installer does not ship it, and per our
-- agreed one-attempt rule we did not try to build it from source). So embeddings are
-- stored as plain REAL[] and the similarity INDEX lives in the Python intelligence
-- service (FAISS, in-memory). We lose nothing we need to apologise for: the
-- intelligence service already owns embedding generation and clustering, so owning
-- its own index is coherent architecture, not a workaround. Postgres remains the
-- durable store of the resolved cluster assignments and the case graph.
--
-- If a demo machine DOES have pgvector, swapping back is a two-line change:
--   embedding vector(384) + CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)
-- and nothing else in the schema or the API moves.
--
-- Dimension 384 matches the pretrained multilingual sentence-transformer
-- (paraphrase-multilingual-MiniLM-L12-v2). Multilingual is not optional here: the
-- seed data mixes English/Hindi phrasings of the same fault, and a monolingual model
-- would fail to merge them. Pretrained only — no model training (out of scope).
--
-- The Python intelligence service is the ONLY writer of these columns. The Java API
-- treats them as opaque bytes and never does vector math.

ALTER TABLE reports ADD COLUMN embedding          REAL[];
ALTER TABLE faults  ADD COLUMN centroid_embedding REAL[];

COMMENT ON COLUMN reports.embedding IS
  '384-dim sentence embedding, written by the Python intelligence service. Similarity index (FAISS) lives in that service, not in Postgres.';
COMMENT ON COLUMN faults.centroid_embedding IS
  '384-dim fault centroid for recurrence matching, written by the Python intelligence service.';
