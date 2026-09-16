"""应用元数据配置 —— 产品名、公司名、版本号、描述、版权等都在这里改

pet.spec（exe 版本信息）和 build_installer.iss（安装包信息）都从这里读取。
exe 的「文件说明」和安装包的「描述」分开配置，可以不一样。

修改后重新打包即可生效。
"""

# ====================== 在这里改 ======================

# 产品名称（exe 属性「产品名称」+ 安装包名称 + 开始菜单/桌面快捷方式名）
PRODUCT_NAME = "净无欲-王涵桌面电子宠物"

# 公司名称（exe 属性「公司」+ 安装包发布者）
COMPANY_NAME = "锐尘ruichen"

# 版本号（语义化：主.次.修订）
# 构建时也可用环境变量 PET_VERSION 覆盖（优先级更高）
VERSION = "0.4.0"

# 产品版本号（exe 属性「产品版本」，通常跟 VERSION 一致或用大版本号如 "1.0"）
# 构建时也可用环境变量 PET_PRODUCT_VERSION 覆盖（优先级更高）
PRODUCT_VERSION = "0.4.0"

# —— exe 文件属性（右键 pet.exe → 属性 → 详细信息）——
# 文件说明（exe 属性「文件说明」，通常跟产品名一致或更简短）
EXE_FILE_DESCRIPTION = "净无欲-王涵桌面电子宠物"

# 内部名称（exe 属性「内部名称」，一般不用改）
INTERNAL_NAME = "pet"

# 原始文件名（一般不用改）
ORIGINAL_FILENAME = "pet.exe"

# —— 安装包（Inno Setup）——
# 安装包描述（安装向导里显示的说明文字，可以写得详细些）
INSTALLER_DESCRIPTION = "净无欲-王涵桌面电子宠物安装程序"

# 安装包 URL（发布者主页、支持页、更新页）
APP_URL = "https://github.com/mmfyxyk/DesktopPet-Jingwuyu--Wanghan"

# —— 共用 ——
# 版权信息（exe + 安装包都用）
LEGAL_COPYRIGHT = "© 2025-2026 mmfyxyk. 基于 MIT License 开源。"

# ======================================================


def get_version() -> str:
    """获取版本号：环境变量 PET_VERSION 优先，否则用上面的 VERSION"""
    import os
    return os.environ.get("PET_VERSION", VERSION)
