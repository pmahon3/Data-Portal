@AC-4 @AC-5 @UC-5.1
Feature: Granting access by choosing from the file tree
  An administrator can grant access by ticking items in the file tree instead of typing paths.
  The selection becomes the same rules typing would make (AC-5: a file, or a folder and
  everything in it, including files added later), with no conversion beyond them: files are
  never collapsed into a folder, and under a filter only the files the filter shows are granted
  (AC-4). The rules are shown in plain words before they are saved.
  Cases: workstreams/access-control/USE-CASE-INSTANCES.md (opensci_infra).

  Background:
    Given the bucket "study" contains:
      | path                        |
      | study/patient-7/scan.nii    |
      | study/patient-7/notes.txt   |
      | study/patient-8/scan.nii    |
      | study/protocol.pdf          |
    And the admin has opened "study"

  Scenario: A ticked folder grants everything in it including files added later
    When the admin ticks "patient-7/"
    Then the rules are exactly "study/patient-7/*"
    And the preview says "alice can read:"
    And the preview says "everything in study/patient-7/, including files added later"
    And the preview says "1 rule."

  Scenario: Ticked files are granted one by one
    When the admin ticks "protocol.pdf"
    And the admin expands "patient-8/"
    And the admin ticks "scan.nii"
    Then the rules are exactly "study/patient-8/scan.nii, study/protocol.pdf"
    And the preview says "2 rules."

  Scenario: Ticking every file in a folder still grants only those files
    When the admin expands "patient-8/"
    And the admin ticks "scan.nii"
    Then the rules are exactly "study/patient-8/scan.nii"

  Scenario: A partly ticked folder grants the ticked files
    When the admin ticks "patient-7/"
    And the admin expands "patient-7/"
    And the admin ticks "notes.txt"
    Then the rules are exactly "study/patient-7/scan.nii"

  Scenario: The bucket itself grants everything in it
    When the admin ticks "study"
    Then the rules are exactly "study/*"
    And the preview says "everything in study/, including files added later"

  Scenario: Under a filter a folder grants only the files the filter shows
    When the admin filters for "*.nii"
    And the admin ticks "study"
    Then the rules are exactly "study/patient-7/scan.nii, study/patient-8/scan.nii"

  Scenario: Under a filter a folder matching it is granted file by file
    When the admin filters for "*patient-7*"
    And the admin ticks "patient-7/"
    Then the rules are exactly "study/patient-7/notes.txt, study/patient-7/scan.nii"
