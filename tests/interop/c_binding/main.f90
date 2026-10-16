interface
  subroutine c_routine() bind(C, name="c_routine")
  end subroutine
end interface
call c_routine
end