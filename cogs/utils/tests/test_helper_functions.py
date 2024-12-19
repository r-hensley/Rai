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
        
if __name__ == '__main__':
    unittest.main()