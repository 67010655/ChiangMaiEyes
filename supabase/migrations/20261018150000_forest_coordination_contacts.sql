-- PRODUCT_BRIEF #7: approval status is public; personal contact details require
-- a confirmed login. No new roles, assignments, or public personal directory.
begin;

create or replace function public.cme_forest_contact_status(p_forest_ids text[])
returns jsonb language plpgsql stable security definer set search_path='' as $$
begin
  if p_forest_ids is null or cardinality(p_forest_ids) not between 1 and 3 then
    raise exception 'เลือกป่าได้ครั้งละ 1–3 แห่ง' using errcode='22023';
  end if;
  return coalesce((select jsonb_agg(jsonb_build_object(
    'forest_id',f.forest_id,
    'has_representative',exists(select 1 from public.cme_memberships m
      join auth.users u on u.id=m.user_id
      where m.forest_id=f.forest_id and m.status='approved'
        and u.email_confirmed_at is not null and nullif(u.email,'') is not null)
  ) order by f.forest_id) from public.cme_forests f where f.forest_id=any(p_forest_ids)), '[]'::jsonb);
end $$;

create or replace function public.cme_forest_contacts(p_forest_ids text[])
returns jsonb language plpgsql stable security definer set search_path='' as $$
begin
  if not exists(select 1 from auth.users where id=auth.uid() and email_confirmed_at is not null) then
    raise exception 'เข้าสู่ระบบและยืนยันอีเมลก่อนดูผู้ประสานงาน' using errcode='42501';
  end if;
  if p_forest_ids is null or cardinality(p_forest_ids) not between 1 and 3 then
    raise exception 'เลือกป่าได้ครั้งละ 1–3 แห่ง' using errcode='22023';
  end if;
  return coalesce((select jsonb_agg(jsonb_build_object(
    'forest_id',f.forest_id,
    'representatives',coalesce((select jsonb_agg(jsonb_build_object(
      'name',coalesce(nullif(btrim(u.raw_user_meta_data->>'full_name'),''),'ตัวแทนป่าชุมชน'),
      'email',u.email
    ) order by m.created_at,m.id) from public.cme_memberships m
      join auth.users u on u.id=m.user_id
      where m.forest_id=f.forest_id and m.status='approved'
        and u.email_confirmed_at is not null and nullif(u.email,'') is not null),'[]'::jsonb)
  ) order by f.forest_id) from public.cme_forests f where f.forest_id=any(p_forest_ids)), '[]'::jsonb);
end $$;

revoke all on function public.cme_forest_contact_status(text[]),public.cme_forest_contacts(text[]) from public,anon,authenticated;
grant execute on function public.cme_forest_contact_status(text[]) to anon,authenticated,service_role;
grant execute on function public.cme_forest_contacts(text[]) to authenticated;
commit;
