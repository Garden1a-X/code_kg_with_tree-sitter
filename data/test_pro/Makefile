# 编译器设置
CC = gcc
CFLAGS = -Wall -Wextra -std=c99 -g

# 目标文件
OBJS = test_1.o test_2.o

# 默认目标 - 只编译对象文件
all: $(OBJS)
	@echo "编译成功！生成的对象文件: $(OBJS)"

# 编译test_1.c
test_1.o: test_1.c test_2.h
	$(CC) $(CFLAGS) -c test_1.c

# 编译test_2.c
test_2.o: test_2.c test_2.h
	$(CC) $(CFLAGS) -c test_2.c

# 清理生成的文件
clean:
	rm -f $(OBJS)

# 重新编译
rebuild: clean all

# 声明伪目标
.PHONY: all clean rebuild