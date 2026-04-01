create extension if not exists vector;

create unique index if not exists bai_viet_uy_tin_url_unique_idx
on public.bai_viet_uy_tin (url);

create or replace function public.hybrid_search_trusted_articles(
  query_text text,
  query_embedding vector(1024),
  result_limit integer default 5
)
returns table (
  source_type text,
  source_table text,
  primary_id integer,
  label text,
  content text,
  url text,
  lexical_score double precision,
  semantic_score double precision,
  hybrid_score double precision
)
language sql
stable
as $$
  with ranked as (
    select
      'trusted_web_cache'::text as source_type,
      'bai_viet_uy_tin'::text as source_table,
      b.id as primary_id,
      b.tieu_de as label,
      b.noidung as content,
      b.url,
      ts_rank(
        to_tsvector('simple', coalesce(b.tieu_de, '') || ' ' || coalesce(b.noidung, '')),
        plainto_tsquery('simple', query_text)
      ) as lexical_score,
      case when b.embedding is null then 0 else 1 - (b.embedding <=> query_embedding) end as semantic_score
    from public.bai_viet_uy_tin b
  )
  select
    source_type,
    source_table,
    primary_id,
    label,
    content,
    url,
    lexical_score,
    semantic_score,
    (0.35 * lexical_score + 0.65 * semantic_score) as hybrid_score
  from ranked
  where lexical_score > 0 or semantic_score > 0
  order by hybrid_score desc
  limit result_limit;
$$;

create or replace function public.hybrid_search_legal_sources(
  query_text text,
  query_embedding vector(1024),
  result_limit integer default 5
)
returns table (
  source_type text,
  source_table text,
  primary_id integer,
  label text,
  content text,
  url text,
  lexical_score double precision,
  semantic_score double precision,
  hybrid_score double precision
)
language sql
stable
as $$
  with legal_union as (
    select
      'legal_db'::text as source_type,
      'noidung'::text as source_table,
      n.sothutund as primary_id,
      coalesce(n.ky_hieu, n.sohieu, 'noidung') as label,
      n.noidung as content,
      null::text as url,
      ts_rank(
        to_tsvector('simple', coalesce(n.search_text, n.noidung, '')),
        plainto_tsquery('simple', query_text)
      ) as lexical_score,
      case when n.embedding is null then 0 else 1 - (n.embedding <=> query_embedding) end as semantic_score
    from public.noidung n
    union all
    select
      'legal_db'::text as source_type,
      'noidung2'::text as source_table,
      n2.sothutund as primary_id,
      coalesce(n2.ky_hieu, n2.sohieu, 'noidung2') as label,
      n2.noidung as content,
      null::text as url,
      ts_rank(
        to_tsvector('simple', coalesce(n2.search_text, n2.noidung, '')),
        plainto_tsquery('simple', query_text)
      ) as lexical_score,
      case when n2.embedding is null then 0 else 1 - (n2.embedding <=> query_embedding) end as semantic_score
    from public.noidung2 n2
  )
  select
    source_type,
    source_table,
    primary_id,
    label,
    content,
    url,
    lexical_score,
    semantic_score,
    (0.35 * lexical_score + 0.65 * semantic_score) as hybrid_score
  from legal_union
  where lexical_score > 0 or semantic_score > 0
  order by hybrid_score desc
  limit result_limit;
$$;
