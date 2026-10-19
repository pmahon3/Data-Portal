@AC-4 @UC-5.1
Feature: Selecting items while a filter is active
  Requirement AC-4 (docs/requirements/access-control.md): a bulk action acts only
  on the items the user selected. Under a filter the tree shows only part of each
  folder, so a selection made there holds individual files, never a folder, and
  downloading or deleting it can't act on files the filter hid.

  Background:
    Given the bucket "study" contains:
      | path            |
      | study/a.json    |
      | study/b.csv     |
      | study/sub/c.csv |

  @INN-295
  Scenario: Folders can't be selected under a filter
    When the user filters for "*.csv"
    And the user expands "study/"
    Then the checkbox for "study/" is disabled
    And the checkbox for "sub/" is disabled

  @INN-295
  Scenario: Clicking a folder row selects nothing under a filter
    When the user filters for "*.csv"
    And the user clicks the row "study/"
    Then the selection is empty

  @INN-295
  Scenario: Selecting the only visible file in a folder doesn't select the folder
    When the user filters for "*.csv"
    And the user expands "study/"
    And the user expands "sub/"
    And the user clicks the row "c.csv"
    Then the selection is exactly "study/sub/c.csv"

  Scenario: Without a filter, selecting a folder selects everything in it
    When the user clicks the row "study/"
    Then the selection is exactly "study/, study/a.json, study/b.csv, study/sub/, study/sub/c.csv"

  @INN-295
  Scenario: Clicking a folder under "Find in selection" doesn't select the folder
    When the user expands "study/"
    And the user clicks the row "a.json"
    And the user turns on "Find in selection"
    And the user clicks the row "study/"
    Then the selection is exactly "study/a.json"
