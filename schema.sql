create table if not exists users (
  id integer primary key autoincrement,
  username text not null unique,
  password text not null,
  name text not null,
  role_id int(11) not null
);

create table if not exists history (
  id integer primary key autoincrement,
  username text not null,
  schedule_time float not null,
  update_time float default null,
  status text not null,
  test_type text not null,
  test_method text not null,
  test_times text not null,
  test_result text not null,
  test_img_path text not null,
  test_cps_path text not null,
  test_rimg_name text not null
);

create table if not exists config (
  id integer primary key autoincrement,
  username text not null,
  config_name text not null,
  config_value text not null
);