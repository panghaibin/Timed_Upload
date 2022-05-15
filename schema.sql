create table if not exists users (
  id integer primary key autoincrement,
  username text not null unique,
  password text not null,
  name text not null
);

create table if not exists history (
  id integer primary key autoincrement,
  username text not null,
  schedule_time float not null,
  status text not null default 'in_queue',
  test_type text not null,
  test_method text not null,
  test_times text not null,
  test_result text not null,
  test_img_path text not null,
  test_rimg_name text not null
);