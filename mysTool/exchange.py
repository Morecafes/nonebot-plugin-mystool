"""
### 米游币兑换相关
"""
import httpx
import time
import traceback
from typing import Literal, Tuple, Union
from .config import mysTool_config as conf
from .utils import generateDeviceID
from nonebot.log import logger
from .data import UserAccount
from .bbsAPI import get_game_record, get_game_list

URL_GOOD_LIST = "https://api-takumi.mihoyo.com/mall/v1/web/goods/list?app_id=1&point_sn=myb&page_size=20&page={page}&game={game}"
URL_CHECK_GOOD = "https://api-takumi.mihoyo.com/mall/v1/web/goods/detail?app_id=1&point_sn=myb&goods_id={}"
URL_EXCHANGE = "https://api-takumi.mihoyo.com/mall/v1/web/goods/exchange"
HEADERS_GOOD_LIST = {
    "Host":
        "api-takumi.mihoyo.com",
    "Accept":
        "application/json, text/plain, */*",
    "Origin":
        "https://user.mihoyo.com",
    "Connection":
        "keep-alive",
    "x-rpc-device_id": generateDeviceID(),
    "x-rpc-client_type":
        "5",
    "User-Agent":
        conf.device.USER_AGENT_MOBILE,
    "Referer":
        "https://user.mihoyo.com/",
    "Accept-Language":
        "zh-CN,zh-Hans;q=0.9",
    "Accept-Encoding":
        "gzip, deflate, br"
}
HEADERS_EXCHANGE = {
    "Accept":
    "application/json, text/plain, */*",
    "Accept-Encoding":
    "gzip, deflate, br",
    "Accept-Language":
    "zh-CN,zh-Hans;q=0.9",
    "Connection":
    "keep-alive",
    "Content-Type":
    "application/json;charset=utf-8",
    "Host":
    "api-takumi.mihoyo.com",
    "User-Agent":
    conf.device.USER_AGENT_MOBILE,
    "x-rpc-app_version":
    conf.device.X_RPC_APP_VERSION,
    "x-rpc-channel":
    "appstore",
    "x-rpc-client_type":
    "1",
    "x-rpc-device_id": None,
    "x-rpc-device_model":
    conf.device.X_RPC_DEVICE_MODEL_MOBILE,
    "x-rpc-device_name":
    conf.device.X_RPC_DEVICE_NAME_MOBILE,
    "x-rpc-sys_version":
    conf.device.X_RPC_SYS_VERSION
}


class Good:
    """
    商品数据
    """

    def __init__(self, good_dict: dict) -> None:
        self.good_dict = good_dict
        try:
            for func in dir(Good):
                if func.startswith("__"):
                    continue
                getattr(self, func)()
        except KeyError:
            logger.error(conf.LOG_HEAD + "米游币商品数据 - 初始化对象: dict数据不正确")
            logger.debug(conf.LOG_HEAD + traceback.format_exc())

    @property
    def name(self) -> str:
        """
        商品名称
        """
        return self.good_dict["goods_name"]

    @property
    def goodID(self) -> str:
        """
        商品ID(Good_ID)
        """
        return self.good_dict["goods_id"]

    @property
    def price(self) -> int:
        """
        商品价格
        """
        return self.good_dict["price"]

    @property
    def time(self):
        """
        兑换时间
        """
        # "next_time" 为 0 表示任何时间均可兑换或兑换已结束
        # "type" 为 1 时商品只有在指定时间开放兑换；为 0 时商品任何时间均可兑换
        if self.good_dict["type"] != 1 and self.good_dict["next_time"] == 0:
            return None
        else:
            return time.strftime("%Y-%m-%d %H:%M:%S",
                                 time.localtime(self.good_dict["sale_start_time"]))

    @property
    def num(self):
        """
        库存
        """
        if self.good_dict["type"] != 1 and self.good_dict["next_num"] == 0:
            return None
        else:
            return self.good_dict["next_num"]

    @property
    def limit(self) -> Tuple[str, str, Literal["forever", "month"]]:
        """
        限购，返回元组 (已经兑换次数, 最多可兑换次数, 限购类型)
        """
        return (self.good_dict["account_exchange_num"],
                self.good_dict["account_cycle_limit"], self.good_dict["account_cycle_type"])

    @property
    def icon(self) -> int:
        """
        商品图片
        """
        return self.good_dict["icon"]

    @property
    def gamebiz(self) -> str:
        """
        游戏区服(例如: hk4e_cn)
        """
        return self.good_dict["game_biz"]


async def get_good_list(game: Literal["bh3", "ys", "bh2", "wd", "bbs"]) -> Union[list[Good], None]:
    if game == "bh3":
        game = "bh3"
    elif game == "ys":
        game = "hk4e"
    elif game == "bh2":
        game = "bh2"
    elif game == "wd":
        game = "nxx"
    elif game == "bbs":
        game = "bbs"

    error_times = 0
    good_list = []
    page = 1
    get_list = None

    while error_times < conf.MAX_RETRY_TIMES:
        try:
            async with httpx.AsyncClient() as client:
                get_list: httpx.Response = client.get(URL_GOOD_LIST.format(page=page,
                                                                           game=game), headers=HEADERS_GOOD_LIST)
                get_list = get_list.json()["data"]["list"]
            # 判断是否已经读完所有商品
            if get_list == []:
                break
            else:
                good_list += get_list
            page += 1
        except KeyError:
            logger.error(conf.LOG_HEAD + "米游币商品兑换 - 获取商品列表: 服务器没有正确返回")
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            error_times += 1
        except:
            logger.error(conf.LOG_HEAD + "米游币商品兑换 - 获取商品列表: 网络请求失败")
            logger.debug(conf.LOG_HEAD + traceback.format_exc())
            error_times += 1

    if not isinstance(get_list, list):
        return None

    result = []

    for good in good_list:
        # "next_time" 为 0 表示任何时间均可兑换或兑换已结束
        # "type" 为 1 时商品只有在指定时间开放兑换；为 0 时商品任何时间均可兑换
        if good["next_time"] == 0 and good["type"] == 1:
            continue
        else:
            result.append(Good(good))

    return result


class Exchange:
    """
    米游币商品兑换相关(需先初始化对象)
    """
    async def __init__(self, account: UserAccount, goodID: str) -> None:
        self.result = None
        self.goodID = goodID
        self.account = account
        self.content = {
            "app_id": 1,
            "point_sn": "myb",
            "goods_id": goodID,
            "exchange_num": 1,
            "address_id": account.address.addressID
        }
        logger.info(conf.LOG_HEAD +
                    "米游币商品兑换 - 初始化兑换任务: 开始获取商品 {} 的信息".format(goodID))
        try:
            async with httpx.AsyncClient() as client:
                res: httpx.Response = client.get(URL_CHECK_GOOD.format(goodID))
            goodInfo = res.json()["data"]
            if goodInfo["type"] == 2:
                if "stoken" not in account.cookie:
                    logger.error(
                        conf.LOG_HEAD + "米游币商品兑换 - 初始化兑换任务: 商品 {} 为游戏内物品，由于未配置stoken，放弃兑换".format(goodID))
                    self.result = -1
                    return
                if account.cookie["stoken"].find("v2__") == 0 and "mid" not in account.cookie:
                    logger.error(
                        conf.LOG_HEAD + "米游币商品兑换 - 初始化兑换任务: 商品 {} 为游戏内物品，由于stoken为\"v2\"类型，且未配置mid，放弃兑换".format(goodID))
                    self.result = -1
                    return
            # 若商品非游戏内物品，则直接返回，不进行下面的操作
            else:
                return
        except KeyError:
            logger.error(
                conf.LOG_HEAD + "米游币商品兑换 - 初始化兑换任务: 获取商品 {} 的信息时，服务器没有正确返回".format(goodID))
        game_list = await get_game_list()
        record_list = await get_game_record(account)
        for record in record_list:
            if record.uid == account.gameUID.ys:
                self.content.setdefault("uid", record.uid)
                # 例: cn_gf01
                self.content.setdefault("region", record.region)
                # 例: hk4e_cn
                self.content.setdefault("game_biz", goodInfo["game_biz"])
                break

    async def start(self) -> Union[Tuple[bool, dict], None]:
        """
        执行兑换操作

        返回元组 (是否成功, 服务器返回数据)\n
        若服务器没有正确返回，函数返回 `None`
        """
        if self.result == -1:
            logger.error(conf.LOG_HEAD +
                         "商品：{} 未初始化完成，放弃兑换".format(self.goodID))
            return None
        else:
            headers = HEADERS_EXCHANGE
            headers["x-rpc-device_id"] = self.account.deviceID
            try:
                async with httpx.AsyncClient() as client:
                    res: httpx.Response = client.post(
                        URL_EXCHANGE, headers=headers, cookies=self.account.cookie)
                if res.json()["message"] == "OK":
                    logger.info(
                        conf.LOG_HEAD + "米游币商品兑换 - 执行兑换: 商品 {} 兑换成功！可以自行确认。".format(self.goodID))
                    return (True, res.json())
                else:
                    logger.info(
                        conf.LOG_HEAD + "米游币商品兑换 - 执行兑换: 商品 {} 兑换失败，可以自行确认。".format(self.goodID))
                    return (False, res.json())
            except KeyError:
                logger.error(
                    conf.LOG_HEAD + "米游币商品兑换 - 执行兑换: 商品 {} 服务器没有正确返回".format(self.goodID))
                return None
