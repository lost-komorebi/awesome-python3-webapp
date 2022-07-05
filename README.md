# awesome-python3-webapp


1. 客户端（浏览器）发起请求
2. 路由分发请求（这个框架自动帮处理），add_routes函数就是注册路由。
3. 中间件预前处理
   - 打印日志
   - 收集Request（请求）的数据
4. RequestHandler清理参数并调用控制器，Django和Flask把这些处理请求的函数称为view functions
5. 控制器做相关的逻辑判断，有必要时通过ORM框架处理Model的事务。
6. 模型层的主要事务是数据库的查增改删。
7. 控制器再次接管控制权，返回相应的数据。
8. Response_factory根据控制器传过来的数据产生不同的响应。
9. 客户端（浏览器）接收到来自服务器的响应。

