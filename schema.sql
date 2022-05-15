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
  test_date text not null,
  test_times text not null,
  test_check text not null,
  file_path text not null,
  status integer not null
);