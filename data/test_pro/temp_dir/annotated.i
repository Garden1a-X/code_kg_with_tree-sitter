/home/lyk/work/test_pro/test_2.h:1	
/home/lyk/work/test_pro/test_2.h:2	
/home/lyk/work/test_pro/test_2.h:3	
/home/lyk/work/test_pro/test_2.h:4	
/home/lyk/work/test_pro/test_2.h:5	struct Config {
/home/lyk/work/test_pro/test_2.h:6	    int level;
/home/lyk/work/test_pro/test_2.h:7	    int extra;
/home/lyk/work/test_pro/test_2.h:8	};
/home/lyk/work/test_pro/test_2.h:9	
/home/lyk/work/test_pro/test_2.h:10	
/home/lyk/work/test_pro/test_2.h:11	extern int global_flag;
/home/lyk/work/test_pro/test_2.h:12	extern struct Config default_config;
/home/lyk/work/test_pro/test_2.h:13	extern int global_return;
/home/lyk/work/test_pro/test_2.h:24	int external_init(void);
/home/lyk/work/test_pro/test_2.h:25	int get_global(void);
/home/lyk/work/test_pro/test_2.h:26	int get_level(struct Config* conf);
/home/lyk/work/test_pro/test_2.h:27	void call_macros(void);
/home/lyk/work/test_pro/test_1.c:2	
/home/lyk/work/test_pro/test_1.c:3	
/home/lyk/work/test_pro/test_1.c:4	
/home/lyk/work/test_pro/test_1.c:5	
/home/lyk/work/test_pro/test_1.c:6	
/home/lyk/work/test_pro/test_1.c:7	
/home/lyk/work/test_pro/test_1.c:8	void handler_usb() {}
/home/lyk/work/test_pro/test_1.c:9	void handler_eth() {}
/home/lyk/work/test_pro/test_1.c:10	
/home/lyk/work/test_pro/test_1.c:11	struct Device {
/home/lyk/work/test_pro/test_1.c:12	    int id;
/home/lyk/work/test_pro/test_1.c:13	    void (*init)();
/home/lyk/work/test_pro/test_1.c:14	    struct Config* config;
/home/lyk/work/test_pro/test_1.c:15	    int mode;
/home/lyk/work/test_pro/test_1.c:16	};
/home/lyk/work/test_pro/test_1.c:17	
/home/lyk/work/test_pro/test_1.c:18	int global_flag = 1;
/home/lyk/work/test_pro/test_1.c:19	struct Config default_config;
/home/lyk/work/test_pro/test_1.c:20	int global_return;
/home/lyk/work/test_pro/test_1.c:21	
/home/lyk/work/test_pro/test_1.c:22	int get_id(struct Device* dev) {
/home/lyk/work/test_pro/test_1.c:23	    return dev->id;
/home/lyk/work/test_pro/test_1.c:24	}
/home/lyk/work/test_pro/test_1.c:25	
/home/lyk/work/test_pro/test_1.c:26	int get_mode(struct Device* dev) {
/home/lyk/work/test_pro/test_1.c:27	    return dev->mode;
/home/lyk/work/test_pro/test_1.c:28	}
/home/lyk/work/test_pro/test_1.c:29	
/home/lyk/work/test_pro/test_1.c:30	int get_const() {
/home/lyk/work/test_pro/test_1.c:31	    int temp = 100;
/home/lyk/work/test_pro/test_1.c:32	    return temp;
/home/lyk/work/test_pro/test_1.c:33	}
/home/lyk/work/test_pro/test_1.c:34	
/home/lyk/work/test_pro/test_1.c:35	int get_buf_size_macro() {
/home/lyk/work/test_pro/test_1.c:36	    return 1024;
/home/lyk/work/test_pro/test_1.c:37	}
/home/lyk/work/test_pro/test_1.c:38	
/home/lyk/work/test_pro/test_1.c:39	void call_init(struct Device* dev) {
/home/lyk/work/test_pro/test_1.c:40	    dev->init();
/home/lyk/work/test_pro/test_1.c:41	}
/home/lyk/work/test_pro/test_1.c:42	
/home/lyk/work/test_pro/test_1.c:43	void assign_ptrs(struct Device* dev) {
/home/lyk/work/test_pro/test_1.c:44	    dev->init = handler_usb;
/home/lyk/work/test_pro/test_1.c:45	    dev->mode = 3;
/home/lyk/work/test_pro/test_1.c:46	}
/home/lyk/work/test_pro/test_1.c:47	
/home/lyk/work/test_pro/test_1.c:48	void setup_device(struct Device* dev, int mode) {
/home/lyk/work/test_pro/test_1.c:49	    int local_mode = get_mode(dev);
/home/lyk/work/test_pro/test_1.c:50	    dev->mode = local_mode;
/home/lyk/work/test_pro/test_1.c:51	}
/home/lyk/work/test_pro/test_1.c:52	
/home/lyk/work/test_pro/test_1.c:53	int compare_buf_sizes(int custom_size) {
/home/lyk/work/test_pro/test_1.c:54	    return ((custom_size) > (1024) ? (custom_size) : (1024));
/home/lyk/work/test_pro/test_1.c:55	}
