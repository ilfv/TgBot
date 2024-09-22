from time import time
from enum import Enum
from io import BytesIO
from copy import deepcopy
from typing import TYPE_CHECKING, Dict

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from lib.data_classes.image import SessionImageGenExtraSettings
from lib.data_classes.locale_struct import Localization
from lib.database.players import PlayersDB
from lib.image.utils.b64_img_handler import base64_to_img, img_to_base64, img_to_readable_buffer
from lib.image.utils.val_normalizer import ValueNormalizer
from lib.image.for_image.colors import Colors
from lib.image.for_image.flags import Flags
from lib.image.for_image.fonts import Fonts
from lib.image.for_image.icons import StatsIcons
from lib.image.for_image.stats_coloring import colorize
from lib.image.for_image.watermark import Watermark
from lib.logger.logger import get_logger
from lib.utils.color_converter import get_tuple_from_color
from lib.settings.settings import Config
from lib.utils.singleton_factory import singleton
from lib.image.utils.resizer import center_crop
from lib.image.for_image.icons import LeaguesIcons

from lib.locale.locale import Text

if TYPE_CHECKING:
    from lib.data_classes.api.api_data import PlayerGlobalData
    from lib.data_classes.session import SessionDiffData, TankSessionData

    from lib.data_classes.db_player import (AccountSlotsEnum, 
                                            DBPlayer, 
                                            GameAccount, 
                                            ImageSettings,
                                            StatsViewSettings,
                                            WidgetSettings)

_log = get_logger(__file__, 'ImageSessionLogger', 'logs/image_session.log')
_config = Config().get()


class ImageGenMetaData:
    tanks_count = 0
    image_size = (0, 0)
    image_format = 'RGBA'
    blocks = 0
    small_blocks = 0


class BlocksStack():
    def __init__(self):
        self.small_blocks = 0
        self.blocks = 0
        
        self.max_blocks = 3
        self.max_small_blocks = 2
        
    def set_max_blocks(self, blocks: int, small_blocks: int):
        self.max_blocks = blocks
        self.max_small_blocks = small_blocks
        
    def add_blocks(self, val: int):
        if val == 0:
            return
        
        for _ in range(val):
            if self.blocks < self.max_blocks:
                self.blocks += 1
            elif self.small_blocks < self.max_small_blocks:
                self.small_blocks += 1
            else:
                pass
            
    def add_block(self):
        if self.blocks < self.max_blocks:
            self.blocks += 1
        elif self.small_blocks < self.max_small_blocks:
            self.small_blocks += 1
        else:
            pass
        
    def get_blocks(self) -> tuple[int, int]:
        return self.blocks, self.small_blocks
        
    def clear(self):
        self.blocks = 0
        self.small_blocks = 0


class Cache():
    cache_label = Image.open('res/image/other/cached_label.png', formats=['png'])


class RelativeCoordinates():
    def __init__(self, image_size, view_settings: 'StatsViewSettings'):
        """
        Class to store coordinates for labels and stats in an image.

        Args:
        - img_size (tuple): Size of the image (width, height)
        """
        
        self.slots = len(view_settings.common_slots.keys())
        self.rating_slots = len(view_settings.rating_slots.keys())
        self.x_coords = []
        self.x_coords_rating = []
        
        for index in range(self.slots + 1):
            if index == 0:
                continue
            
            self.x_coords.append(image_size[0]//(self.slots + 1) * index)
            
        for index in range(self.rating_slots + 1):
            if index == 0:
                continue
            
            self.x_coords_rating.append(image_size[0]//(self.rating_slots + 1) * index)
            
        self.center_x = image_size[0] // 2
        
    def blocks_labels(self, offset_y):
        return (self.center_x, offset_y + 15)

        # Main stats labels position in the stats block
    def main_stats_labels(self, offset_y) -> Dict[str, tuple]:
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], offset_y + 196)
            
        return coords
        
    def main_stats_icons(self, offset_y, icons_size: tuple[int, int]):
        
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index] - icons_size[1] // 2, offset_y + 40)
            
        return coords
        
    def tank_stats_icons(self, offset_y, icons_size: tuple[int, int]):
        return self.main_stats_icons(offset_y, icons_size)
    
    def rating_stats_icons(self, offset_y, icons_size: tuple[int, int]):
        coords = {}
        
        for index in range(self.rating_slots):
            coords[f'slot_{index + 1}'] = (self.x_coords_rating[index] - icons_size[1] // 2, offset_y + 40)
            
        return coords

    # Main stats values position in the stats block
    def main_stats(self, offset_y):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], offset_y + 97)
            
        return coords

    # Main session stats position in the stats block
    def main_session_stats(self, offset_y):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 140 + offset_y)
        
        return coords

    # Main difference stats position in the stats block
    def main_diff_stats(self, offset_y):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 170 + offset_y)
            
        return coords

    # Rating labels
    def rating_labels(self, offset_y):
        coords = {}
        
        for index in range(self.rating_slots):
            coords[f'slot_{index + 1}'] = (self.x_coords_rating[index], offset_y + 196)
            
        return coords
        
    def rating_stats(self, offset_y):
        coords = {}
        
        for index in range(self.rating_slots):
            coords[f'slot_{index + 1}'] = (self.x_coords_rating[index], offset_y + 97)
        
        return coords
    
    def rating_session_stats(self, offset_y):
        coords = {}
        
        for index in range(self.rating_slots):
            coords[f'slot_{index + 1}'] = (self.x_coords_rating[index], 140 + offset_y)
            
        return coords
        
    def rating_diff_stats(self, offset_y):
        coords = {}
        
        for index in range(self.rating_slots):
            coords[f'slot_{index + 1}'] = (self.x_coords_rating[index], 170 + offset_y)
            
        return coords
        
    def tank_stats_labels(self, offset_y):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 213 + offset_y)
            
        return coords
    
    def short_tank_stats_labels(self, offset_y):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 150 + offset_y)
            
        return coords
        
    def short_tank_stats(self, offset_y: int):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 90 + offset_y)
            
        return coords
        
    def tank_stats(self, offset_y: int):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 105 + offset_y)
            
        return coords
        
    def tank_session_stats(self, offset_y: int):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 150 + offset_y)
            
        return coords
        
    def tank_diff_stats(self, offset_y: int):
        coords = {}
        
        for index in range(self.slots):
            coords[f'slot_{index + 1}'] = (self.x_coords[index], 185 + offset_y)
            
        return coords

    def short_tank_session_stats(self, offset_y: int):
        coords = {}
        
        for i in range(self.slots):
            coords[f'slot_{i + 1}'] = (self.x_coords[i], 120 + offset_y)
            
        return coords


class DiffValues():
    def __init__(self, diff_data: 'SessionDiffData', stats_view_settings: 'StatsViewSettings') -> None:
        """
        Initializes a DiffValues object with the given diff_data.

        Args:
            diff_data ('SessionDiffData'): The diff_data object containing the differences.
            stats_view (StatsViewSettings): The stats_view object containing the settings.

        Returns:
            None
        """
        
        self.val_normalizer = ValueNormalizer()
        self.diff_data = diff_data
        self.stats_view = stats_view_settings.common_slots
        self.rating_view = stats_view_settings.rating_slots
        self.main = {}
        self.rating = {}
        
        for index, (_, value) in enumerate(self.stats_view.items()):
            if value == 'empty':
                continue
            
            stats = getattr(diff_data.main_diff, value)
            
            if value in ['winrate', 'accuracy']:
                self.main.setdefault('slot_' + str(index + 1), (
                    self.val_normalizer.value_add_plus(stats) + self.val_normalizer.winrate(stats))
                )
                
            else:
                self.main.setdefault('slot_' + str(index + 1), (
                    self.val_normalizer.value_add_plus(stats) + self.val_normalizer.adaptive(stats))
                )

        for index, (_, value) in enumerate(self.rating_view.items()):
            if value == 'empty':
                continue
            
            stats = getattr(diff_data.rating_diff, value)
            
            if value in ['winrate', 'accuracy']:
                self.rating.setdefault('slot_' + str(index + 1), (
                    ValueNormalizer.value_add_plus(stats) + self.val_normalizer.winrate(stats)
                    )
                )
                
            else:
                self.rating.setdefault('slot_' + str(index + 1), (
                    ValueNormalizer.value_add_plus(stats) + self.val_normalizer.adaptive(stats)
                    )
                )

    def tank_stats(self, tank_id: int | str):
        tank_id = str(tank_id)
        result = {}
        
        for slot, value in self.stats_view.items():
            stats = getattr(self.diff_data.tank_stats[tank_id], 'd_' + value)
            
            if value == 'empty':
                continue
            
            if value == 'winrate' or value == 'accuracy':
                result[slot] = ValueNormalizer.value_add_plus(stats) + self.val_normalizer.winrate(stats)
            
            else:
                result[slot] = ValueNormalizer.value_add_plus(stats) + self.val_normalizer.adaptive(stats)
            
        return result

class SessionValues():
    def __init__(self, session_data: 'SessionDiffData', stats_view_settings: 'StatsViewSettings') -> None:
        self.val_normalizer = ValueNormalizer()
        self.session_data = session_data
        self.stats_view = stats_view_settings.common_slots
        self.rating_view = stats_view_settings.rating_slots
        self.main = {}
        self.rating = {}
        
        for slot, value in self.stats_view.items():
            if value in ['winrate', 'accuracy']:
                self.main[slot] = self.val_normalizer.winrate(getattr(session_data.main_session, value))
            else:
                self.main[slot] = self.val_normalizer.adaptive(getattr(session_data.main_session, value))

        for slot, value in self.rating_view.items():
            if value in ['winrate', 'accuracy']:
                self.rating[slot] = self.val_normalizer.winrate(getattr(session_data.rating_session, value))
            else:
                self.rating[slot] = self.val_normalizer.adaptive(getattr(session_data.rating_session, value))

    def tank_stats(self, tank_id: int | str):
        tank_id = str(tank_id)
        tank_stats = {}
        
        for slot, value in self.stats_view.items():
            if value in ['winrate', 'accuracy']:
                tank_stats[slot] = self.val_normalizer.winrate(getattr(self.session_data.tank_stats[tank_id], 's_' + value))
            else:
                tank_stats[slot] = self.val_normalizer.adaptive(getattr(self.session_data.tank_stats[tank_id], 's_' + value))
        
        return tank_stats


class Values():
    def __init__(self, data: 'PlayerGlobalData', session_diff: 'SessionDiffData', stats_view: 'StatsViewSettings') -> None:
        """
        Initializes a Values object.

        Args:
            data ('PlayerGlobalData'): The player's global data.
            tank_index (int): The index of the tank in the tankopedia_db list.
        """
        if data is None or session_diff is None:
            raise ValueError('Both data and session_diff must be provided.')
         
        self.val_normalizer = ValueNormalizer()
        stats_data = data.data.statistics
        self.tank_data = data.data.tank_stats
        self.stats_view = stats_view.common_slots
        self.rating_view = stats_view.rating_slots
        self.session_diff = session_diff
        self.main = {}
        self.rating = {}
        
        for slot, value in self.stats_view.items():
            if value in ['winrate', 'accuracy']:
                self.main[slot] = self.val_normalizer.winrate(getattr(stats_data.all, value))
            else:
                self.main[slot] = self.val_normalizer.adaptive(getattr(stats_data.all, value))

        # Define the rating statistics
        for slot, value in self.rating_view.items():
            if value in ['winrate', 'accuracy']:
                self.rating[slot] = self.val_normalizer.winrate(getattr(stats_data.rating, value))
            else:
                self.rating[slot] = self.val_normalizer.adaptive(getattr(stats_data.rating, value))

    def get_tank_stats(self, tank_id: int | str):
        tank_stats = {}
        
        for slot, value in self.stats_view.items():
            if value in ['winrate', 'accuracy']:
                tank_stats[slot] = self.val_normalizer.winrate(getattr(self.tank_data[str(tank_id)].all, value))
            else:
                tank_stats[slot] = self.val_normalizer.adaptive(getattr(self.tank_data[str(tank_id)].all, value))
                
        return tank_stats

class StatsBlockSize:
    main_stats = 240
    rating_stats = 240
    full_tank_stats = 260
    short_tank_stats = 200


class BlockOffsets:
    first_indent = 80
    block_indent = 20
    horizontal_indent = 50


class ImageSize:
    max_height: int = 1350
    min_height: int = 380
    max_width: int = 800
    min_width: int = 525

class LayoutDefiner:
    def __init__(
            self, 
            data: 'SessionDiffData',
            player_data: 'PlayerGlobalData',
            image_settings: 'ImageSettings', 
            extra: SessionImageGenExtraSettings,
            stats_view_settings: 'StatsViewSettings',
            widget_settings: 'WidgetSettings',
            widget_mode: bool
        ) -> None:
        self.player_data = player_data
        self.stack = BlocksStack()
        self.widget_mode = widget_mode
        self.session_data = data
        self.image_height = ImageSize.min_height
        self.image_width = ImageSize.min_width
        self.blocks = 1
        self.small_blocks = 0
        self.max_fullstats_blocks = widget_settings.max_stats_blocks if widget_mode else 3
        self.max_short_stats_blocks = widget_settings.max_stats_small_blocks if widget_mode else 2
        self.image_settings = image_settings
        self.include_rating = False
        self.extra = extra
        self.widget_settings = widget_settings
        self.stats_view = stats_view_settings
        
        self.nickname_box = []
        self.nickname_params = {}
        self.clan_tag_params = {}
    
    def _calculate_stats_blocks(self) -> None:
        self.stack.set_max_blocks(
            self.widget_settings.max_stats_blocks if self.widget_mode else 3,
            self.widget_settings.max_stats_small_blocks if self.widget_mode else 2
        )
        if self.session_data.tank_stats is not None:
            tanks_count = len(self.session_data.tank_stats)
        else:
            tanks_count = 0
            
        self.stack.add_blocks(tanks_count)
        
        if not self.image_settings.disable_rating_stats:
            include_rating = self.session_data.rating_session.battles > 0
        else:
            include_rating = False
            
        self.include_rating = include_rating
        
        if not (self.widget_mode and self.widget_settings.disable_main_stats_block):
            self.stack.add_block()
            
        if self.widget_mode and (self.widget_settings.disable_main_stats_block and tanks_count == 0):
            self.stack.add_block()

        if include_rating:
            self.stack.add_block()
        
        self.blocks, self.small_blocks = self.stack.get_blocks()
        _log.debug(f'Blocks: {self.blocks}, small blocks: {self.small_blocks}')
        
    def _calculate_image_size(self) -> None:
        if self.blocks == 3 and self.small_blocks == 2:
            self.image_height = ImageSize.max_height 
            self.image_width = ImageSize.max_width
            return
        
        self.image_height = BlockOffsets.first_indent
        
        self.image_height += (
            BlockOffsets.block_indent * (self.blocks + self.small_blocks) +
            StatsBlockSize.full_tank_stats * self.blocks +
            StatsBlockSize.short_tank_stats * self.small_blocks
        )
        
        if self.widget_settings.adaptive_width and self.widget_mode:
            self.image_width = (
                len(
                    max(
                        self.stats_view.common_slots.keys(),
                        self.stats_view.rating_slots.keys(),
                    )
                ) * (ImageSize.max_width // 4)
            )
            if self.image_width < ImageSize.min_width:
                self.image_width = ImageSize.min_width
        else:
            self.image_width = ImageSize.max_width
        
    def _prepare_background(self):
        self.layout_map = Image.new(
            'RGBA',
            (self.image_width, self.image_height),
            (0, 0, 0, 0)
        )
        
    def get_blocks_count(self) -> tuple[int, int]:
        return self.blocks, self.small_blocks
    
    def _block_size_calculate(
        self, 
        current_block: int,
        include_rating: bool,
        widget_settings: 'WidgetSettings', 
        widget_mode: bool
        ) -> int:
        
        if widget_mode and widget_settings.disable_main_stats_block:
            if current_block == 0 and include_rating:
                return StatsBlockSize.rating_stats
            else:
                return StatsBlockSize.full_tank_stats
        
        if current_block == 0:
            return StatsBlockSize.main_stats
        if current_block == 1 and include_rating:
            return StatsBlockSize.rating_stats
        else:
            return StatsBlockSize.full_tank_stats

    def create_rectangle_map(self) -> Image.Image:
        self._calculate_stats_blocks()
        self._calculate_image_size()
        self._prepare_background()
        
        _log.debug(
            f'img size: {self.image_width}x{self.image_height} blocks: {self.blocks} small: {self.small_blocks}'
        )
        drawable_layout = ImageDraw.Draw(self.layout_map)
        current_offset = BlockOffsets.first_indent
        
        if self.image_settings.hide_nickname:
            self.player_data.nickname = 'Player'
        if self.image_settings.hide_clan_tag:
            self.player_data.data.clan_tag = None
        if self.player_data.data.clan_tag is not None:
            tag = {
                'text':     f'[{self.player_data.data.clan_stats.tag}]',
                'font':     Fonts.roboto_30,
            }
            nickname = {
                'text':     self.player_data.nickname,
                'font':     Fonts.roboto_30,
            }

            tag_length = drawable_layout.textlength(**tag) + 10
            nick_length = drawable_layout.textlength(**nickname)
            full_length = tag_length + nick_length
            
            nickname_text_params = {
                "xy": (ImageSize.max_width//2 - tag_length//2, 20),
                "text" : self.player_data.nickname,
                "font" : Fonts.roboto_30,
                "anchor" : 'ma',
                "fill" : self.image_settings.nickname_color
            }
            
            self.nickname_params = nickname_text_params
            
            clan_tag_text_params = {
                "xy": (ImageSize.max_width//2 + full_length//2 - tag_length//2, 20),
                "text" : tag['text'],
                "font" : Fonts.roboto_30,
                "anchor" : 'ma',
                "fill" : self.image_settings.clan_tag_color
            }
            
            self.clan_tag_params = clan_tag_text_params
            
        else:
            nickname = {
                'text':     self.player_data.nickname,
                'font':     Fonts.roboto_30,
            }
            full_length = drawable_layout.textlength(**nickname)

            nickname_text_params = {
                "xy": (ImageSize.max_width//2, 20),
                "text" : self.player_data.nickname,
                "font" : Fonts.roboto_30,
                "anchor" : 'ma',
                "fill" : self.image_settings.nickname_color
            }
            
            self.nickname_params = nickname_text_params
            
            del nickname_text_params['fill']
            
        
        color = (
            *get_tuple_from_color(self.widget_settings.stats_block_color),
            int(abs(1 - self.widget_settings.background_transparency) * 255)
        )
        if not self.widget_mode:
            color = (255, 255, 255, 255)
            
        drawable_layout.rounded_rectangle(
            [
                self.image_width//2 - full_length//2 - 10,
                12,
                self.image_width//2 + full_length//2 + 10,
                60
            ],
            radius=10,
            fill=color,
        )
            
        for block in range(self.blocks):
            drawable_layout.rounded_rectangle(
                (
                    BlockOffsets.horizontal_indent, 
                    current_offset,
                    self.image_width - BlockOffsets.horizontal_indent,
                    self._block_size_calculate(
                        block,
                        self.include_rating,
                        self.widget_settings,
                        self.widget_mode
                        ) + current_offset
                ),
                fill=color,
                radius=25
            )
            current_offset += (
                self._block_size_calculate(
                    block,
                    self.include_rating,
                    self.widget_settings,
                    self.widget_mode
                    )
                ) + BlockOffsets.block_indent
         
        if self.small_blocks > 0:
            for _ in range(self.small_blocks):
                drawable_layout.rounded_rectangle(
                    (
                        BlockOffsets.horizontal_indent, 
                        current_offset, 
                        self.image_width - BlockOffsets.horizontal_indent,
                        current_offset + StatsBlockSize.short_tank_stats
                    ),
                    fill=color,
                    radius=25
                )
                current_offset += StatsBlockSize.short_tank_stats + BlockOffsets.block_indent
        
        return self.layout_map
    
    
class ImageGenReturnTypes(Enum):
    PIL_IMAGE = 1
    BYTES_IO = 2
    BASE64 = 3


@singleton
class ImageGenSession():
    leagues = LeaguesIcons()
    colors = Colors()
    pdb = PlayersDB()
    flags = Flags()
    fonts = Fonts()
    stats_view: 'StatsViewSettings' = None
    session_values: SessionValues = None
    diff_data: 'SessionDiffData' = None
    diff_values: DiffValues = None
    image: Image.Image = None
    text: Localization = None
    img_size: tuple = None
    values: Values = None
    coord = None
    data = None
    
    
    def _load_image(self, bytes_ot_path: str | bytes | None) -> None:
        if bytes_ot_path is not None:
            image = Image.open(_config.image.default_bg_path, formats=['png'])
        else:
            image = Image.open(bytes_ot_path, formats=['png'])
            
        if image.mode != 'RGBA':
            image = image.convert('RGBA')

        self.image = center_crop(image, (ImageSize.max_width, ImageSize.max_height))

    def _load_image_by_rules(self, member: 'DBPlayer | None' = None) -> None:
        if member is not None:
            if (member.image is not None) and member.use_custom_image:
                self.image = base64_to_img(member.image)
                return
                
        self._load_image(_config.image.default_bg_path)

    def generate(
            self, 
            data: 'PlayerGlobalData',
            diff_data: 'SessionDiffData',
            player: 'DBPlayer',
            slot: 'AccountSlotsEnum',
            force_image_settings: 'ImageSettings | None' = None,
            force_stats_view: 'StatsViewSettings | None' = None,
            extra: SessionImageGenExtraSettings = SessionImageGenExtraSettings(),
            output_type: ImageGenReturnTypes = ImageGenReturnTypes.BYTES_IO,
            widget_mode: bool = False,
            test = False,
            debug_label = False,
            force_locale: str | None = None,
            **extra_image_settings) -> BytesIO | Image.Image | str:
        """
        Generates an image based on the provided data and settings.

        Args:
            data (PlayerGlobalData): The global player data.
            diff_data (SessionDiffData): The session diff data.
            player (DBPlayer): The player object.
            server (DBServer | None): The server object or None.
            slot (AccountSlotsEnum): The account slot enum.
            force_image_settings (ImageSettings | None, optional): The image settings to force. Defaults to None.
            extra (ImageGenExtraSettings, optional): The extra image generation settings. Defaults to ImageGenExtraSettings().
            output_type (ImageGenReturnTypes, optional): The type of output to generate. Defaults to ImageGenReturnTypes.BYTES_IO.
            widget_mode (bool, optional): Whether to generate the image in widget mode. Defaults to False.
            test (bool, optional): Whether to test the image generation. Defaults to False.
            debug_label (bool, optional): Whether to generate the debug label. Defaults to True.
            force_locale (str | None, optional): The locale to force. Defaults to None.

        Returns:
            BytesIO | Image.Image | str: The generated image in the specified output type.

        Raises:
            TypeError: If the output_type is not an instance of ImageGenReturnTypes.
        """

        if force_locale is not None:
            self.text = Text().load(lang=force_locale)
        
        
        self.game_account: 'GameAccount' = getattr(player.game_accounts, slot.name)
        self.player = player
        self.image_settings = deepcopy(self.game_account.image_settings if force_image_settings is None else force_image_settings)
        stats_view_settings = self.game_account.stats_view_settings if force_stats_view is None else force_stats_view

        for settings_name in extra_image_settings:
            setattr(self.image_settings, settings_name, extra_image_settings[settings_name])
        
        self.layout_definer = LayoutDefiner(
            player_data=data,
            data=diff_data,
            image_settings=self.image_settings,
            extra=extra,
            stats_view_settings=stats_view_settings,
            widget_settings=self.game_account.widget_settings,
            widget_mode=widget_mode
        )
        start_time = time()
        self.layout_map = self.layout_definer.create_rectangle_map()
        self.blocks, self.small_blocks = self.layout_definer.get_blocks_count()
        self.include_rating = self.layout_definer.include_rating
        self.diff_data = diff_data
        self.data = data
        self.diff_values = DiffValues(diff_data, stats_view_settings)
        self.session_values = SessionValues(diff_data, stats_view_settings)
        self.values = Values(data, diff_data, stats_view_settings)
        self.current_offset = 0
        self.metadata = ImageGenMetaData()
        
        if diff_data.tank_stats is not None:
            self.tank_iterator = iter(diff_data.tank_stats)
        else: 
            self.tank_iterator = iter([])
        self.stats_view = stats_view_settings
        
        self.metadata.tanks_count = len(diff_data.tank_stats.keys()) if diff_data.tank_stats is not None else 0

        self._load_image_by_rules(player)
        
        if self.image.mode != 'RGBA':
            self.image = self.image.convert('RGBA')

        self.metadata.image_format = self.image.format
        self.image = center_crop(self.image, self.layout_map.size)
        self.img_size = self.image.size
        self.metadata.image_size = self.img_size
        
        self.draw_background(
            self.layout_map, 
            widget_mode=widget_mode, 
            widget_settings=self.game_account.widget_settings   
        )
        img_draw = ImageDraw.Draw(self.image)

        self.text = Text().get()
        self.coord = RelativeCoordinates(self.img_size, self.game_account.stats_view_settings)
        self.current_offset = BlockOffsets.first_indent
        
        self.metadata.blocks = self.blocks
        self.metadata.small_blocks = self.small_blocks
        
        if not widget_mode:

            self.draw_nickname(img_draw)
            if not self.image_settings.disable_flag:
                self.draw_flag()
        
            self.draw_main_stats_block(img_draw)
            self.blocks -= 1
            self.current_offset += StatsBlockSize.main_stats + BlockOffsets.block_indent

            if self.include_rating:
                self.draw_rating_stats_block(img_draw)
                self.blocks -= 1
                self.current_offset += StatsBlockSize.rating_stats + BlockOffsets.block_indent

            for _ in range(self.blocks):
                try:
                    curr_tank = self.diff_data.tank_stats[next(self.tank_iterator)]
                    curr_tank.tank_name = curr_tank.tank_id if curr_tank.tank_name == 'Unknown' else curr_tank.tank_name
                except StopIteration:
                    break
                self.draw_tank_stats_block(img_draw, curr_tank)
                self.current_offset += StatsBlockSize.full_tank_stats + BlockOffsets.block_indent
                self.blocks -= 1
        
            for _ in range(self.small_blocks):
                try:
                    curr_tank = self.diff_data.tank_stats[next(self.tank_iterator)]
                except StopIteration:
                    break
                self.draw_short_tank_stats_block(img_draw, curr_tank)
                self.small_blocks -= 1
                self.current_offset += StatsBlockSize.short_tank_stats + BlockOffsets.block_indent
            
            self.draw_watermark()
            
        else:
            if not self.game_account.widget_settings.disable_nickname:
                self.draw_nickname(img_draw)
                if not self.image_settings.disable_flag:
                    self.draw_flag()
            
            
            if not self.game_account.widget_settings.disable_main_stats_block:
                self.draw_main_stats_block(img_draw)
                self.blocks -= 1
                self.current_offset += StatsBlockSize.main_stats + BlockOffsets.block_indent

            if self.include_rating:
                self.draw_rating_stats_block(img_draw)
                self.blocks -= 1
                self.current_offset += StatsBlockSize.rating_stats + BlockOffsets.block_indent
                
            for _ in range(self.blocks):
                try:
                    curr_tank = self.diff_data.tank_stats[next(self.tank_iterator)]
                except StopIteration:
                    break
                self.draw_tank_stats_block(img_draw, curr_tank)
                self.current_offset += StatsBlockSize.full_tank_stats + BlockOffsets.block_indent
                self.blocks -= 1
        
            for _ in range(self.small_blocks):
                try:
                    curr_tank = self.diff_data.tank_stats[next(self.tank_iterator)]
                except StopIteration:
                    break
                self.draw_short_tank_stats_block(img_draw, curr_tank)
                self.small_blocks -= 1
                self.current_offset += StatsBlockSize.short_tank_stats + BlockOffsets.block_indent
            
            self.draw_watermark()
        
        if debug_label:
            self.draw_debug_label(img_draw)

        _log.debug(f'Image generated in {round(time() - start_time, 4)} seconds')

        if test:
            self.image.show()
            return
        
        if output_type == ImageGenReturnTypes.BYTES_IO:
            return img_to_readable_buffer(self.image)
        
        elif output_type == ImageGenReturnTypes.PIL_IMAGE:
            return self.image
        
        elif output_type == ImageGenReturnTypes.BASE64:
            return img_to_base64(self.image)

        else:
            raise TypeError(f'output_type must be an instance of ImageGenReturnTypes, not {output_type.__class__.__name__}')
    
    def draw_main_stats_block(self, image_draw: ImageDraw.ImageDraw) -> None:
        self.draw_block_label(image_draw, self.text.for_image.main)
        self.draw_main_stats_icons()
        self.draw_main_labels(image_draw)
        self.draw_main_stats(image_draw)
        self.draw_main_session_stats(image_draw)
        self.draw_main_diff_stats(image_draw)
        
    def draw_rating_stats_block(self, image_draw: ImageDraw.ImageDraw) -> None:
        self.draw_block_label(image_draw, self.text.for_image.rating)
        self.draw_rating_icons()
        self.draw_rating_labels(image_draw)
        self.draw_rating_stats(image_draw)
        self.draw_rating_session_stats(image_draw)
        self.draw_rating_diff_stats(image_draw)
        
    def draw_tank_stats_block(self, image_draw: ImageDraw.ImageDraw, curr_tank: 'TankSessionData') -> None:
        self.draw_tank_block_label(image_draw, curr_tank)
        self.draw_tank_stats_icons()
        self.draw_tank_labels(image_draw)
        self.draw_tank_stats(image_draw, curr_tank)
        self.draw_tank_session_stats(image_draw, curr_tank)
        self.draw_tank_diff_stats(image_draw, curr_tank)
        
    def draw_short_tank_stats_block(self, image_draw: ImageDraw.ImageDraw, curr_tank: 'TankSessionData') -> None:
        self.draw_tank_block_label(image_draw, curr_tank)
        self.draw_tank_stats_icons()
        self.draw_short_tank_labels(image_draw)
        self.draw_short_tank_stats(image_draw, curr_tank)
        self.draw_short_tank_session_stats(image_draw, curr_tank)

    def draw_main_stats_icons(self) -> None:
        for slot, value in self.stats_view.common_slots.items():
            icon: Image.Image = getattr(StatsIcons, value)
            self.image.paste(
                icon,
                self.coord.main_stats_icons(self.current_offset, icon.size)[slot],
                icon
            )
        
    def draw_rating_icons(self) -> None:
        for slot, value in self.stats_view.rating_slots.items():
            if value == 'rating':
                icon = self.get_rating_icon(self.values.rating[slot])
            else:
                icon = getattr(StatsIcons, value)
                
            self.image.paste(
                icon,
                self.coord.rating_stats_icons(self.current_offset, icon.size)[slot],
                icon
            )
        
    def draw_tank_stats_icons(self) -> None:
        for slot, value in self.stats_view.common_slots.items():
            icon: Image.Image = getattr(StatsIcons, value)
            self.image.paste(
                icon,
                self.coord.tank_stats_icons(self.current_offset, icon.size)[slot],
                icon
            )
        
    def draw_block_label(self, img_draw: ImageDraw.ImageDraw, text: str) -> None:
        img_draw.text(
            self.coord.blocks_labels(self.current_offset),
            text,
            font=self.fonts.roboto_20,
            anchor='mm',
            fill=self.image_settings.main_text_color
        )
        
    def draw_tank_block_label(self, img_draw: ImageDraw.ImageDraw, curr_tank: 'TankSessionData') -> None:
        img_draw.text(
            self.coord.blocks_labels(self.current_offset),
            f'{self.tank_type_handler(curr_tank.tank_type)} {curr_tank.tank_name} {self.tank_tier_handler(curr_tank.tank_tier)}',
            font=self.fonts.roboto_25,
            anchor='mm',
            fill=self.image_settings.main_text_color
        )
    
    def draw_background(
            self, 
            rectangle_map: Image.Image, 
            widget_mode: bool,
            widget_settings: 'WidgetSettings'
        ) -> None:
        
        if self.image_settings.disable_stats_blocks:
            return
        
        if widget_mode:
            image = Image.new('RGBA', rectangle_map.size, (0, 0, 0, 0))
            if widget_settings.disable_bg:
                bg = Image.new('RGBA', rectangle_map.size, (0, 0, 0, 0))
                self.image = image
                self.image.paste(rectangle_map, (0, 0), rectangle_map)
                return
                
            elif widget_settings.use_bg_for_stats_blocks:
                bg = self.image.copy()
                _log.debug(f'BG size: {bg.size}')
                _log.debug(f'Rectangle map size: {rectangle_map.size}')
                self.image = image
                if bg.size != rectangle_map.size:
                    bg = bg.resize(rectangle_map.size)
                
                self.image.paste(bg, (0, 0), rectangle_map)

            else:
                bg = Image.new('RGBA', rectangle_map.size, (0, 0, 0, 0))
                self.image.putalpha(int(255 * abs(widget_settings.background_transparency - 1.0)))

        else:
            bg = self.image.copy()
            
            gaussian_filter = ImageFilter.GaussianBlur(radius=self.image_settings.glass_effect)

            if self.image_settings.glass_effect > 0:
                bg = bg.filter(gaussian_filter)
            if self.image_settings.stats_blocks_transparency > 0:
                bg = ImageEnhance.Brightness(bg).enhance(self.image_settings.stats_blocks_transparency)
                bg.filter(gaussian_filter)

        self.image.paste(bg, (0, 0), rectangle_map)

    def draw_debug_label(self, img: ImageDraw.ImageDraw) -> None:
        bbox = img.textbbox(
            (self.img_size[0] // 2 - 100, self.img_size[1] // 2),
            text='DEBUG PREVIEW',
            font=self.fonts.roboto_27
        )
        img.rectangle(bbox, fill=(127, 127, 127, 200))
        img.text(
            (self.img_size[0] // 2 - 100, self.img_size[1] // 2),
            text='DEBUG PREVIEW',
            font=self.fonts.roboto_27,
            fill=(20, 200, 20, 200)
        )
        img.text(
            (20, self.img_size[1] - 240),
            text=\
                f'INFO:\n'\
                f'=========================\n'\
                f'SIZE: {self.metadata.image_size}\n'\
                f'FORMAT: {self.metadata.image_format}\n'\
                f'LAYOUT DEFINER PROPS:\n'\
                f'=========================\n'\
                f'TANKS COUNT: {self.metadata.tanks_count}\n'\
                f'BLOCKS: {self.metadata.blocks}\n'\
                f'SMALL BLOCKS: {self.metadata.small_blocks}\n'\
                f'SLOTS CONFIG: \n'
                    f'{self.game_account.stats_view_settings.common_slots}\n'
                    f'{self.game_account.stats_view_settings.rating_slots}\n',
            align='left',
            font=self.fonts.roboto_17
        )
        
    def draw_watermark(self):
        self.image.paste(Watermark.v1, (
            self.img_size[0] - 40, 
            self.img_size[1] // 2 - Watermark.v1.size[1] // 2
            ), 
        Watermark.v1)
        
    def tank_type_handler(self, tank_type: str):
        match tank_type:
            case 'heavyTank':
                return 'ﬄ • '
            case 'mediumTank':
                return 'ﬃ • '
            case 'lightTank':
                return 'ﬂ • '
            case 'AT-SPG':
                return 'ﬁ • '
            case _:
                return '� • ' 
            
    def tank_tier_handler(self, tier: int):
        match tier:
            case 1:
                return ' • I'
            case 2:
                return ' • II'
            case 3:
                return ' • III'
            case 4:
                return ' • IV'
            case 5:
                return ' • V'
            case 6:
                return ' • VI'
            case 7:
                return ' • VII'
            case 8:
                return ' • VIII'
            case 9:
                return ' • IX'
            case 10:
                return ' • X'
            case _:
                return ' • ?'

    def draw_nickname(self, img: ImageDraw.ImageDraw):
        if self.image_settings.hide_nickname:
            self.data.nickname = 'Player'
        if self.image_settings.hide_clan_tag:
            self.data.data.clan_tag = None
            
        if not self.image_settings.hide_nickname:
            if self.data.data.clan_tag is None:
                img.text(**self.layout_definer.nickname_params)
                return
            
            img.text(**self.layout_definer.nickname_params)
            img.text(**self.layout_definer.clan_tag_params)

    def draw_main_labels(self, img: ImageDraw.ImageDraw):
        coords = self.coord.main_stats_labels(self.current_offset)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=getattr(self.text.for_image, value),
                font=self.fonts.roboto_20,
                anchor='ma',
                align='center',
                fill=self.image_settings.stats_text_color
            )

    def draw_main_stats(self, img: ImageDraw.ImageDraw):
        coords = self.coord.main_stats(self.current_offset)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=self.values.main[slot],
                font=self.fonts.roboto_30,
                anchor='ma',
                align='center',
                fill=colorize(
                    value,
                    self.values.main[slot],
                    self.image_settings.stats_color
                    ) if self.image_settings.colorize_stats else self.image_settings.stats_color
                )

    def draw_main_diff_stats(self, img: ImageDraw.ImageDraw):
        coords = self.coord.main_diff_stats(self.current_offset)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=self.diff_values.main[slot],
                font=self.fonts.roboto,
                anchor='ma',
                align='center',
                fill=self.value_colors(getattr(self.diff_data.main_diff, value))
            )
    
    def draw_main_session_stats(self, img: ImageDraw.ImageDraw):
        coords = self.coord.main_session_stats(self.current_offset)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=self.session_values.main[slot],
                font=self.fonts.roboto_27,
                anchor='ma',
                align='center',
                fill=colorize(
                    value,
                    self.session_values.main[slot],
                    Colors.l_grey
                ) if self.image_settings.colorize_stats else self.image_settings.stats_color
            )

    def draw_rating_labels(self, img: ImageDraw.ImageDraw):
        coords = self.coord.rating_labels(self.current_offset)
        for slot, value in self.stats_view.rating_slots.items():
            if value == 'rating':
                text = self._rating_label_handler()
            else:
                text = getattr(self.text.for_image, value)
            img.text(
                coords[slot],
                text=text,
                font=self.fonts.roboto_20,
                anchor='ma',
                align='center',
                fill=self.image_settings.stats_text_color
            )

    def draw_rating_stats(self, img: ImageDraw.ImageDraw):
        coords = self.coord.rating_stats(self.current_offset)
        
        for slot, value in self.stats_view.rating_slots.items():
            if value == 'rating' and self.data.data.statistics.rating.calibration_battles_left != 0:
                text = f'{abs(self.data.data.statistics.rating.calibration_battles_left - 10)} / 10'
            else:
                text = self.values.rating[slot]
            img.text(
                coords[slot],
                text=str(text),
                font=self.fonts.roboto_30,
                anchor='ma',
                align='center',
                fill=colorize(
                    value,
                    self.values.rating[slot],
                    self.image_settings.stats_color,
                    rating=True
                    ) if self.image_settings.colorize_stats else self.image_settings.stats_color
                )

    def draw_rating_session_stats(self, img: ImageDraw.ImageDraw):
        coords = self.coord.rating_session_stats(self.current_offset)
        
        for slot, value in self.stats_view.rating_slots.items():
            img.text(
                coords[slot],
                text=self.session_values.rating[slot],
                font=self.fonts.roboto_27,
                anchor='ma',
                align='center',
                fill=colorize(
                    value,
                    self.session_values.rating[slot],
                    Colors.l_grey,
                    rating=True
                ) if self.image_settings.colorize_stats else self.image_settings.stats_color
            )

    def _rating_label_handler(self):
        rating = self.data.data.statistics.rating.rating
        if self.data.data.statistics.rating.calibration_battles_left == 10:
            text = self.text.for_image.no_rating
        elif self.data.data.statistics.rating.calibration_battles_left > 0:
            text = self.text.for_image.leagues.calibration
        elif rating >= 3000 and rating < 4000:
            text = self.text.for_image.leagues.gold
        elif rating >= 4000 and rating < 5000:
            text = self.text.for_image.leagues.platinum
        elif rating > 5000:
            text = self.text.for_image.leagues.brilliant
        else:
            text = self.text.for_image.leagues.no_league
        return text

    def draw_rating_diff_stats(self, img: ImageDraw.ImageDraw):
        coords = self.coord.rating_diff_stats(self.current_offset)
        
        for slot, value in self.stats_view.rating_slots.items():
            img.text(
                coords[slot],
                text=self.diff_values.rating[slot],
                font=self.fonts.roboto,
                anchor='ma',
                align='center',
                fill=self.value_colors(
                    getattr(self.diff_data.rating_diff, value), 
                    reverse=True if value == 'leaderboard_position' else False
                )
            )

    def draw_tank_stats(self, img: ImageDraw.ImageDraw, curr_tank: 'TankSessionData'):
        coords = self.coord.tank_stats(self.current_offset)
        tank_stats = self.values.get_tank_stats(curr_tank.tank_id)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=tank_stats[slot],
                font=self.fonts.roboto_30,
                anchor='ma',
                align='center',
                fill=colorize(
                    value,
                    tank_stats[slot],
                    self.image_settings.stats_color
                ) if self.image_settings.colorize_stats else self.image_settings.stats_color
            )
    
    def draw_short_tank_stats(self, img: ImageDraw.ImageDraw, curr_tank: 'TankSessionData'):
        coords = self.coord.short_tank_stats(self.current_offset)
        tank_stats = self.values.get_tank_stats(curr_tank.tank_id)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=tank_stats[slot],
                font=self.fonts.roboto_30,
                anchor='ma',
                align='center',
                fill=colorize(
                    value,
                    tank_stats[slot],
                    self.image_settings.stats_color
                    ) if self.image_settings.colorize_stats else self.image_settings.stats_color
            )

    def draw_short_tank_session_stats(self, img: ImageDraw.ImageDraw, curr_tank: 'TankSessionData'):
        coords = self.coord.short_tank_session_stats(self.current_offset)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=ValueNormalizer.value_add_plus(
                    getattr(curr_tank, f'd_{value}')
                ) + self.session_values.tank_stats(curr_tank.tank_id)[slot],
                font=self.fonts.roboto,
                anchor='ma',
                align='center',
                fill=self.value_colors(getattr(curr_tank, f'd_{value}'))
            )
                
    def draw_tank_diff_stats(self, img: ImageDraw.ImageDraw, curr_tank: 'TankSessionData'):
        coords = self.coord.tank_diff_stats(self.current_offset)
        tank_stats = self.diff_values.tank_stats(curr_tank.tank_id)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=tank_stats[slot],
                font=self.fonts.roboto,
                anchor='ma',
                align='center',
                fill=self.value_colors(getattr(curr_tank, f'd_{value}'))
            )

    def draw_tank_session_stats(self, img: ImageDraw.ImageDraw, curr_tank: 'TankSessionData'):
        coords = self.coord.tank_session_stats(self.current_offset)
        tank_stats = self.session_values.tank_stats(curr_tank.tank_id)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=tank_stats[slot],
                font=self.fonts.roboto_27,
                anchor='ma',
                align='center',
                fill=colorize(
                    value,
                    tank_stats[slot],
                    Colors.l_grey
                ) if self.image_settings.colorize_stats else self.image_settings.stats_color
            )

    def draw_tank_labels(self, img: ImageDraw.ImageDraw):
        coords = self.coord.tank_stats_labels(self.current_offset)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=getattr(self.text.for_image, value),
                font=self.fonts.roboto_20,
                anchor='ma',
                align='center',
                fill=self.image_settings.stats_text_color
            )
            
    def draw_short_tank_labels(self, img: ImageDraw.ImageDraw):
        coords = self.coord.short_tank_stats_labels(self.current_offset)
        for slot, value in self.stats_view.common_slots.items():
            img.text(
                coords[slot],
                text=getattr(self.text.for_image, value),
                font=self.fonts.roboto_20,
                anchor='ma',
                align='center',
                fill=self.image_settings.stats_text_color
            )
    
    def draw_flag(self) -> None:
        match self.data.region:
            case 'ru':
                self.image.paste(self.flags.ru, (10, 10), self.flags.ru)
            case 'eu':
                self.image.paste(self.flags.eu, (10, 10), self.flags.eu)
            case 'com':
                self.image.paste(self.flags.usa, (10, 10), self.flags.usa)
            case 'asia':
                self.image.paste(self.flags.china, (10, 10), self.flags.china)

    def value_colors(self, value: int | float, reverse: bool = False) -> tuple:
        if not isinstance(value, (int, float)):
            return Colors.grey
        value = round(value, 2)
        if value > 0:
            return self.image_settings.positive_stats_color if not reverse else self.image_settings.negative_stats_color
        if value < 0:
            return self.image_settings.negative_stats_color if not reverse else self.image_settings.positive_stats_color
        if value == 0:
            return Colors.grey
        
    def get_rating_icon(self, value: int | str) -> Image.Image:
        try:
            value = int(value)
        except ValueError:
            return LeaguesIcons.calibration
        if value in range(3000, 3999):
            return LeaguesIcons.gold
        elif value in range(4000, 4999):
            return LeaguesIcons.platinum
        elif value > 5000:
            return LeaguesIcons.brilliant
        else:
            return LeaguesIcons.empty
