program hello
    implicit none

    integer :: fu

    open(file="hello.txt", newunit=fu, action="write", status="replace")
    write(fu, *) "Hello, File!"
    close(fu)
end program