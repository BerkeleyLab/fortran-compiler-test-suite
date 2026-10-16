character(len=7) :: greeting
call get_environment_variable("GREETING", greeting)
print *, greeting
end