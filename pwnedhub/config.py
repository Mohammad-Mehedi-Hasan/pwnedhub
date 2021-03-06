from common.config import SharedBaseConfig, SharedDevConfig, SharedTestConfig, SharedProdConfig

class BaseConfig(SharedBaseConfig):

    SESSION_COOKIE_HTTPONLY = False
    PERMANENT_SESSION_LIFETIME = 3600 # 1 hour
    MARKDOWN_EXTENSIONS = [
        'markdown.extensions.tables',
        'markdown.extensions.extra',
        'markdown.extensions.attr_list',
        'markdown.extensions.fenced_code',
    ]

class Development(SharedDevConfig, BaseConfig):

    pass

class Test(SharedTestConfig, BaseConfig):

    pass

class Production(SharedProdConfig, BaseConfig):

    pass
