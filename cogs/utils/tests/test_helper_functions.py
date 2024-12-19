# test some functions in cogs.utils.helper_functions.py using unittest

import unittest
from cogs.utils.helper_functions import split_text_into_segments

class TestSplitText(unittest.TestCase):
    """Test splitting text of various lengths into segments. The code should take texts of various lengths and
    split it into a list of strings of length specified."""
    
    def test_one(self):
        """Test splitting a text of length 1 into segments of length 1."""
        self.assertEqual(split_text_into_segments("a", 1), ["a"])
        
    def test_two(self):
        """Test splitting a text of length 2 into segments of length 1."""
        self.assertEqual(split_text_into_segments("ab", 1), ["a", "b"])
        
    def test_three(self):
        """Test splitting a text of length 4 into segments of length 2."""
        self.assertEqual(split_text_into_segments("abcd", 2), ["ab", "cd"])
        
    def test_four(self):
        """Test splitting a text of length 2500 into segments of length 1024."""
        self.assertEqual(split_text_into_segments("a"*2500, 1024), ["a"*1024, "a"*1024, "a"*452])
        
    def test_five(self):
        """Test splitting a text of length 0 into segments of length 1."""
        self.assertEqual(split_text_into_segments("", 1), [''])
        
    def test_six(self):
        """Test splitting a text of length 8000 into segments of length 1024."""
        self.assertEqual(split_text_into_segments("a"*8000, 1024), ["a"*1024] * 7 + ["a"*832])
        
    def test_seven(self):
        """Test splitting long text with spaces"""
        # ignore spelling errors for next line in Pycharm
        # noinspection SpellCheckingInspection
        s = ("Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore "
             "et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut "
             "aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum "
             "dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui "
             "officia deserunt mollit anim id est laborum.")
        # noinspection SpellCheckingInspection
        result = ['Lorem ipsum dolor sit amet, consectetur', 'adipiscing elit, sed do eiusmod tempor incididunt',
                  'ut labore et dolore magna aliqua. Ut enim ad', 'minim veniam, quis nostrud exercitation ullamco',
                  'laboris nisi ut aliquip ex ea commodo consequat.', 'Duis aute irure dolor in reprehenderit in',
                  'voluptate velit esse cillum dolore eu fugiat', 'nulla pariatur. Excepteur sint occaecat cupidatat',
                  'non proident, sunt in culpa qui officia deserunt', 'mollit anim id est laborum.']
        self.assertEqual(split_text_into_segments(s, 50), result)
        
    def test_eight(self):
        s = ("""Traceback (most recent call last):
  File "/home/pi/Documents/bot-venv/lib/python3.11/site-packages/discord/client.py", line 449, in _run_event
    await coro(*args, **kwargs)
  File "/home/pi/Documents/Rai/cogs/logger.py", line 586, in on_raw_message_edit
    await self.log_raw_payload(payload)
  File "/home/pi/Documents/Rai/cogs/logger.py", line 814, in log_raw_payload
    await self.log_edit_event(old_message.to_discord_message(), new_message, levenshtein_distance, logging_channel)
  File "/home/pi/Documents/Rai/cogs/logger.py", line 442, in log_edit_event
    await utils.safe_send(channel, embed=emb)
  File "/home/pi/Documents/Rai/cogs/utils/BotUtils/bot_utils.py", line 153, in safe_send
    return await destination.send(content, embed=embed, delete_after=delete_after, file=file, view=view)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/Documents/bot-venv/lib/python3.11/site-packages/discord/abc.py", line 1618, in send
    data = await state.http.send_message(channel.id, params=params)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/pi/Documents/bot-venv/lib/python3.11/site-packages/discord/http.py", line 758, in request
    raise HTTPException(response, data)
discord.errors.HTTPException: 400 Bad Request (error code: 50035): Invalid Form Body
In embeds.0.footer.icon_url: Not a well formed URL.""")
        result = ['Traceback (most recent call last):\n  File "/home/pi/Documents/bot-venv/lib/python3.11/site-packages/discord/client.py", line 449, in _run_event\n    await coro(*args, **kwargs)\n  File "/home/pi/Documents/Rai/cogs/logger.py", line 586, in on_raw_message_edit\n    await self.log_raw_payload(payload)\n  File "/home/pi/Documents/Rai/cogs/logger.py", line 814, in log_raw_payload\n    await self.log_edit_event(old_message.to_discord_message(), new_message, levenshtein_distance, logging_channel)',
 'File "/home/pi/Documents/Rai/cogs/logger.py", line 442, in log_edit_event\n    await utils.safe_send(channel, embed=emb)\n  File "/home/pi/Documents/Rai/cogs/utils/BotUtils/bot_utils.py", line 153, in safe_send\n    return await destination.send(content, embed=embed, delete_after=delete_after, file=file, view=view)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^',
 'File "/home/pi/Documents/bot-venv/lib/python3.11/site-packages/discord/abc.py", line 1618, in send\n    data = await state.http.send_message(channel.id, params=params)\n           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n  File "/home/pi/Documents/bot-venv/lib/python3.11/site-packages/discord/http.py", line 758, in request\n    raise HTTPException(response, data)\ndiscord.errors.HTTPException: 400 Bad Request (error code: 50035): Invalid Form Body',
 'In embeds.0.footer.icon_url: Not a well formed URL.']
        # split every 500
        self.assertEqual(split_text_into_segments(s, 500), result)
        
if __name__ == '__main__':
    unittest.main()