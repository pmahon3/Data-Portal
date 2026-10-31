@AC-4 @UC-5.1
Feature: Selecting items while a filter is active
  Requirement AC-4 (docs/requirements/access-control.md): a bulk action acts only
  on the items the user selected. Under a filter the tree shows only part of each
  folder, so selecting a folder there selects only the files in it that the filter
  shows (decision C3), and downloading or deleting it can't act on files the filter
  hid. A folder whose own path matches the filter shows everything in it, so it's
  selected whole.

  Background:
    Given the bucket "study" contains:
      | path            |
      | study/a.json    |
      | study/b.csv     |
      | study/sub/c.csv |

  @INN-295
  Scenario: Under a filter, a folder selects only the files the filter shows
    When the user filters for "*.csv"
    And the user clicks the row "study/"
    Then the selection is exactly "study/b.csv, study/sub/c.csv"

  @INN-295
  Scenario: Clicking the folder again deselects what it showed
    When the user filters for "*.csv"
    And the user clicks the row "study/"
    And the user clicks the row "study/"
    Then the selection is empty

  @INN-295
  Scenario: A folder shows as partly selected when only some of what it shows is
    When the user filters for "*.csv"
    And the user expands "study/"
    And the user clicks the row "b.csv"
    Then the checkbox for "study/" is partly checked

  @INN-295
  Scenario: Selecting the only visible file in a folder doesn't select the folder
    When the user filters for "*.csv"
    And the user expands "study/"
    And the user expands "sub/"
    And the user clicks the row "c.csv"
    Then the selection is exactly "study/sub/c.csv"

  Scenario: A folder whose own name matches the filter is selected whole
    When the user filters for "*sub*"
    And the user expands "study/"
    And the user clicks the row "sub/"
    Then the selection is exactly "study/sub/, study/sub/c.csv"

  Scenario: Without a filter, selecting a folder selects everything in it
    When the user clicks the row "study/"
    Then the selection is exactly "study/, study/a.json, study/b.csv, study/sub/, study/sub/c.csv"

  @INN-295
  Scenario: Under "Find in selection", clicking a folder acts only on the selected items it shows
    When the user expands "study/"
    And the user clicks the row "a.json"
    And the user turns on "Find in selection"
    And the user clicks the row "study/"
    Then the selection is empty
