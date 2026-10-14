-- Run once in the Supabase SQL editor. Tombstones are intentionally retained.
create table if not exists public.pinboard_items (
  owner_id uuid not null references auth.users(id) on delete cascade,
  id uuid not null,
  record jsonb not null,
  updated_at timestamptz not null,
  device_id text not null,
  primary key (owner_id, id),
  constraint item_owner_matches check (record->>'ownerId' = owner_id::text),
  constraint item_id_matches check (record->>'id' = id::text)
);
alter table public.pinboard_items enable row level security;
drop policy if exists owner_access on public.pinboard_items;
create policy owner_access on public.pinboard_items for all to authenticated
  using (auth.uid() = owner_id) with check (auth.uid() = owner_id);
revoke all on public.pinboard_items from anon;
grant select, insert, update on public.pinboard_items to authenticated;
create or replace function public.merge_pinboard_item(record jsonb)
returns void language plpgsql security invoker set search_path = public
as $$
declare
  supplied_owner uuid := (record->>'ownerId')::uuid;
  supplied_id uuid := (record->>'id')::uuid;
  supplied_time timestamptz := (record->>'updatedAt')::timestamptz;
  supplied_device text := record->>'deviceId';
begin
  if auth.uid() is null or supplied_owner is distinct from auth.uid() then
    raise exception 'Unauthorized';
  end if;
  if coalesce(record->>'kind', '') not in ('task', 'note') or coalesce(record->>'color', '') not in ('sage', 'yellow', 'blue', 'rose')
     or jsonb_typeof(record->'title') is distinct from 'string'
     or length(record->>'title') not between 1 and 300
     or jsonb_typeof(record->'body') is distinct from 'string'
     or length(record->>'body') > 100000
     or jsonb_typeof(record->'completed') is distinct from 'boolean'
     or supplied_device is null or supplied_time is null or supplied_id is null
     or not (record ?& array['createdAt', 'dueDate', 'deletedAt']) then
    raise exception 'Invalid item';
  end if;
  perform (record->>'createdAt')::timestamptz;
  if record->>'deletedAt' is not null then perform (record->>'deletedAt')::timestamptz; end if;
  if record->>'dueDate' is not null then perform (record->>'dueDate')::date; end if;
  insert into public.pinboard_items as existing (owner_id, id, record, updated_at, device_id)
    values (supplied_owner, supplied_id, record, supplied_time, supplied_device)
    on conflict (owner_id, id) do update set record = excluded.record,
      updated_at = excluded.updated_at, device_id = excluded.device_id
    where (excluded.updated_at, excluded.device_id collate "C") >
          (existing.updated_at, existing.device_id collate "C");
end;
$$;
revoke all on function public.merge_pinboard_item(jsonb) from public, anon;
grant execute on function public.merge_pinboard_item(jsonb) to authenticated;
