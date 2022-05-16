-- 2022.05.16 12:30
-- users增加role_id字段
alter table users add role_id int(11) not null default 0;
-- 2022.05.16 14:52
-- history增加test_cps_path字段
alter table history add test_cps_path text not null default '';