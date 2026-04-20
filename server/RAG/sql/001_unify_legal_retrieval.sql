create extension if not exists vector;
create extension if not exists unaccent;

alter table public.noidung2 add column if not exists sothutund bigserial primary key;
alter table public.noidung2 add column if not exists noidung text;
alter table public.noidung2 add column if not exists sohieu text;
alter table public.noidung2 add column if not exists sothutund_cha bigint;
alter table public.noidung2 add column if not exists search_text text;
alter table public.noidung2 add column if not exists search_vector vector(1024);
alter table public.noidung2 add column if not exists modified_by text;
alter table public.noidung2 add column if not exists modified_at timestamptz;
alter table public.noidung2 add column if not exists embedding vector(1024);
alter table public.noidung2 add column if not exists loai_muc text;
alter table public.noidung2 add column if not exists ky_hieu text;
alter table public.noidung2 add column if not exists thu_tu integer;
alter table public.noidung2 add column if not exists rela text[];
alter table public.noidung2 add column if not exists rela_embed vector(1024);
alter table public.noidung2 add column if not exists min_km double precision;
alter table public.noidung2 add column if not exists max_km double precision;
alter table public.noidung2 add column if not exists ten_van_ban text;
alter table public.noidung2 add column if not exists source_file_name text;
alter table public.noidung2 add column if not exists source_file_type text;
alter table public.noidung2 add column if not exists doc_type text;
alter table public.noidung2 add column if not exists file_id uuid;
alter table public.noidung2 add column if not exists chunk_index integer;
alter table public.noidung2 add column if not exists section_path text;
alter table public.noidung2 add column if not exists page_start integer;
alter table public.noidung2 add column if not exists page_end integer;
alter table public.noidung2 add column if not exists raw_text text;
alter table public.noidung2 add column if not exists extracted_json jsonb default '{}'::jsonb;
alter table public.noidung2 add column if not exists metadata jsonb default '{}'::jsonb;
alter table public.noidung2 add column if not exists is_validated boolean default false;
alter table public.noidung2 add column if not exists validation_errors jsonb default '[]'::jsonb;
alter table public.noidung2 add column if not exists is_active boolean default true;
alter table public.noidung2 add column if not exists created_at timestamptz default now();
alter table public.noidung2 add column if not exists updated_at timestamptz default now();

create index if not exists idx_noidung2_file_id on public.noidung2(file_id);
create index if not exists idx_noidung2_sohieu on public.noidung2(sohieu);
create index if not exists idx_noidung2_active_validated on public.noidung2(is_active, is_validated);
create index if not exists idx_noidung2_metadata_gin on public.noidung2 using gin(metadata);

create or replace view public.legal_merged_view as
select
    'noidung'::text as source_table,
    'legal_db'::text as source_type,
    n.sothutund,
    n.sothutund_cha,
    n.noidung,
    n.sohieu,
    n.embedding,
    n.embedding as search_vector,
    n.noidung as search_text,
    n.loai_muc,
    n.ky_hieu,
    n.thu_tu,
    n.rela,
    n.rela_embed,
    n.min_km,
    n.max_km,
    null::text as ten_van_ban,
    null::text as source_file_name,
    null::text as source_file_type,
    'manual_input'::text as doc_type,
    null::uuid as file_id,
    null::integer as chunk_index,
    n.duong_dan_phan_cap as section_path,
    null::integer as page_start,
    null::integer as page_end,
    n.noidung as raw_text,
    '{}'::jsonb as extracted_json,
    jsonb_build_object('scope', 'manual') as metadata,
    true as is_validated,
    '[]'::jsonb as validation_errors,
    true as is_active,
    null::text as modified_by,
    null::timestamptz as modified_at,
    null::timestamptz as created_at,
    null::timestamptz as updated_at
from public.noidung n
where n.embedding is not null

union all

select
    'noidung2'::text as source_table,
    case
        when coalesce(n2.metadata ->> 'scope', 'global') = 'session' then 'user_upload'
        else 'admin_upload'
    end as source_type,
    n2.sothutund,
    n2.sothutund_cha,
    n2.noidung,
    n2.sohieu,
    n2.embedding,
    coalesce(n2.search_vector, n2.embedding) as search_vector,
    coalesce(n2.search_text, n2.noidung) as search_text,
    n2.loai_muc,
    n2.ky_hieu,
    n2.thu_tu,
    n2.rela,
    n2.rela_embed,
    n2.min_km,
    n2.max_km,
    n2.ten_van_ban,
    n2.source_file_name,
    n2.source_file_type,
    n2.doc_type,
    n2.file_id,
    n2.chunk_index,
    n2.section_path,
    n2.page_start,
    n2.page_end,
    n2.raw_text,
    coalesce(n2.extracted_json, '{}'::jsonb) as extracted_json,
    coalesce(n2.metadata, '{}'::jsonb) as metadata,
    coalesce(n2.is_validated, false) as is_validated,
    coalesce(n2.validation_errors, '[]'::jsonb) as validation_errors,
    coalesce(n2.is_active, true) as is_active,
    n2.modified_by,
    n2.modified_at,
    n2.created_at,
    n2.updated_at
from public.noidung2 n2
where coalesce(n2.is_active, true) = true
  and coalesce(n2.is_validated, false) = true
  and n2.embedding is not null;

create or replace function public.match_legal_docs_unified(
    vector_truy_van vector(1024),
    van_ban_truy_van text,
    nguong_khop double precision default 0.45,
    so_luong_ket_qua integer default 10,
    so_km_truy_van double precision default null,
    p_session_id text default null
)
returns table (
    source_table text,
    source_type text,
    sothutund bigint,
    sothutund_cha bigint,
    noidung text,
    sohieu text,
    so_hieu text,
    ten_van_ban text,
    source_file_name text,
    source_file_type text,
    doc_type text,
    file_id uuid,
    chunk_index integer,
    section_path text,
    page_start integer,
    page_end integer,
    loai_muc text,
    ky_hieu text,
    thu_tu integer,
    rela text[],
    min_km double precision,
    max_km double precision,
    metadata jsonb,
    is_validated boolean,
    km_phu_hop boolean,
    do_tuong_dong double precision
)
language sql
stable
as $$
with query_ctx as (
    select
        lower(unaccent(coalesce(van_ban_truy_van, ''))) as qtxt,
        regexp_split_to_array(lower(unaccent(coalesce(van_ban_truy_van, ''))), '\s+') as qtokens
),
eligible as (
    select l.*
    from public.legal_merged_view l
    where l.embedding is not null
      and (
          l.source_table = 'noidung'
          or coalesce(l.metadata ->> 'scope', 'global') = 'global'
          or coalesce(l.metadata ->> 'session_id', '') = coalesce(p_session_id, '__no_session__')
      )
),
scored as (
    select
        e.*,
        greatest(
            1 - (e.embedding <=> vector_truy_van),
            1 - (coalesce(e.search_vector, e.embedding) <=> vector_truy_van)
        ) as dense_score,
        case
            when qc.qtxt <> '' and lower(unaccent(coalesce(e.search_text, e.noidung, ''))) like '%' || qc.qtxt || '%'
                then 1.0
            else 0.0
        end as exact_score,
        (
            select coalesce(sum(
                case
                    when token <> '' and lower(unaccent(coalesce(e.search_text, e.noidung, ''))) like '%' || token || '%'
                        then 1
                    else 0
                end
            ), 0)
            from unnest(qc.qtokens) as token
        )::double precision / greatest(array_length(qc.qtokens, 1), 1) as lexical_score,
        case
            when so_km_truy_van is null then false
            when e.min_km is null and e.max_km is null then false
            when e.max_km is null then so_km_truy_van >= e.min_km
            else so_km_truy_van between e.min_km and e.max_km
        end as km_match
    from eligible e
    cross join query_ctx qc
),
ranked as (
    select
        scored.*,
        (
            dense_score * 0.72
            + exact_score * 0.18
            + lexical_score * 0.10
            + case when km_match then 0.08 else 0 end
        ) as hybrid_score
    from scored
)
select
    source_table,
    source_type,
    sothutund,
    sothutund_cha,
    noidung,
    sohieu,
    sohieu as so_hieu,
    ten_van_ban,
    source_file_name,
    source_file_type,
    doc_type,
    file_id,
    chunk_index,
    section_path,
    page_start,
    page_end,
    loai_muc,
    ky_hieu,
    thu_tu,
    rela,
    min_km,
    max_km,
    metadata,
    is_validated,
    km_match as km_phu_hop,
    hybrid_score as do_tuong_dong
from ranked
where hybrid_score >= nguong_khop
order by hybrid_score desc, source_table asc, sothutund asc
limit greatest(so_luong_ket_qua, 1);
$$;
