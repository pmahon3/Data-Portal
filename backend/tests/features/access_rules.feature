Feature: What a policy allows
  A policy gives a user one action on a literal path: one file ("bucket/path/file"),
  a folder and everything in it ("bucket/folder/*"), or everything ("*").
  Requirements in docs/requirements/access-control.md.

  @AC-5 @UC-5.1
  Scenario Outline: A policy covers exactly what its path names
    Given the user holds "<action>" on "<policy>"
    Then the user <may> "<action>" "<path>"

    Examples: Folder policies cover the folder and everything in it
      | policy           | action | path                   | may     |
      | qa-bucket/fold/* | read   | qa-bucket/fold/a.txt   | may     |
      | qa-bucket/fold/* | read   | qa-bucket/fold/sub/b   | may     |
      | qa-bucket/fold/* | delete | qa-bucket/fold/        | may     |

    @INN-292
    Examples: A policy doesn't reach paths that only start with the same letters
      | policy           | action | path                          | may     |
      | qa-bucket/fold   | read   | qa-bucket/folder-secret/x.txt | may not |
      | qa-bucket/fold   | read   | qa-bucket/fold/a.txt          | may not |
      | qa-bucket/fold/* | read   | qa-bucket/folder-secret/x.txt | may not |
      | qa-bucket/fold/* | read   | qa-bucket/fold                | may not |

    @INN-292
    Examples: A file policy names one file, and "." is just a dot
      | policy                       | action | path                             | may     |
      | qa-authz/shared/notes.txt    | read   | qa-authz/shared/notes.txt        | may     |
      | qa-authz/shared/notes.txt    | read   | qa-authz/shared/notes.txt.secret | may not |
      | qa-authz/data/report.csv.bak | write  | qa-authz/data/reportXcsv.bak     | may not |

    @INN-289
    Examples: Characters that mean something in patterns are ordinary
      | policy             | action | path               | may     |
      | qa-bucket/a[b.bin  | read   | qa-bucket/a[b.bin  | may     |
      | qa-bucket/(x)+.csv | read   | qa-bucket/(x)+.csv | may     |
      | qa-bucket/fold/*   | read   | qa-bucket/a[b.bin  | may not |

    Examples: Actions must match, and "*" holds every action
      | policy           | action | path                 | may     |
      | *                | delete | anything/at/all.nii  | may     |
      | qa-bucket/fold/* | *      | qa-bucket/fold/a.txt | may     |

  @AC-2 @INN-293
  Scenario Outline: Access to one file gives no action on the folders above it
    Given the user holds "<held>" on "qa-authz/study/p7/summary.csv"
    Then the user may not "<action>" "<folder>"

    Examples:
      | held   | action | folder               |
      | read   | read   | qa-authz/study/      |
      | write  | write  | qa-authz/study/p7/   |
      | delete | delete | qa-authz/study/      |
      | write  | write  | qa-authz/            |

  @AC-1
  Scenario Outline: Browsing shows only the folders on the way to what the user holds
    Given the user holds "<held>" on "<policy>"
    Then the folder "<folder>" is <shown> when browsing to "<action>"

    Examples:
      | policy                        | held  | action | folder                 | shown     |
      | qa-authz/study/p7/summary.csv | read  | read   | qa-authz/              | shown     |
      | qa-authz/study/p7/summary.csv | read  | read   | qa-authz/study/        | shown     |
      | qa-authz/study/p7/summary.csv | read  | read   | qa-authz/study/p7/     | shown     |
      | qa-authz/study/p7/summary.csv | read  | read   | qa-authz/study/other/  | not shown |
      | qa-authz/study/p7/summary.csv | write | write  | qa-authz/study/p7/     | shown     |
      | qa-authz/study/p7/summary.csv | write | read   | qa-authz/study/        | not shown |
      | qa-authz/study/p7/*           | read  | read   | qa-authz/study/        | shown     |
      | qa-authz/study/p7/*           | read  | read   | qa-authz/study/p7/sub/ | shown     |
      | qa-bucket/fold/*              | read  | read   | qa-bucket/folder-secret/ | not shown |
      | qa-bucket/fold                | read  | read   | qa-bucket/folder-secret/ | not shown |
      | qa-bucket/study/x.csv         | read  | read   | qa-bucket/stu          | not shown |

  @AC-5
  Scenario Outline: Saved policy paths are literal
    When an administrator saves a policy on "<entered>"
    Then it is saved as "<saved>"

    Examples:
      | entered                 | saved                  |
      | /qa-bucket/fold/*       | qa-bucket/fold/*       |
      | qa-bucket//fold/a.txt   | qa-bucket/fold/a.txt   |
      | *                       | *                      |
      | qa-bucket/a[b.bin       | qa-bucket/a[b.bin      |

  @AC-5
  Scenario Outline: A "*" anywhere but the end is refused
    When an administrator saves a policy on "<entered>"
    Then it is refused

    Examples:
      | entered               |
      | qa-bucket/*/anat/     |
      | qa-bucket/fold*       |
      | qa-bucket/fold/*.csv  |
      | /                     |

  @AC-8
  Scenario Outline: A policy allows nothing after its end date
    Given the user holds "read" on "qa-bucket/fold/*" until "<ends>"
    Then the user <may> "read" "qa-bucket/fold/a.txt"
    And the folder "qa-bucket/fold/" is <shown> when browsing to "read"

    Examples:
      | ends       | may     | shown     |
      | 2000-01-01 | may not | not shown |
      | today      | may     | shown     |
      | 2999-12-31 | may     | shown     |

  @AC-8
  Scenario: An ended policy leaves the user's other policies working
    Given the user holds "read" on "qa-bucket/fold/*" until "2000-01-01"
    And the user holds "read" on "qa-bucket/fold/a.txt"
    Then the user may "read" "qa-bucket/fold/a.txt"
    And the user may not "read" "qa-bucket/fold/b.txt"

  @AC-10
  Scenario Outline: A folder policy leaves out what it excludes
    Given the user holds "read" on "qa-bucket/study/*" leaving out "qa-bucket/study/sub-03/*, qa-bucket/study/notes.txt"
    Then the user <may> "read" "<path>"

    Examples:
      | path                                 | may     |
      | qa-bucket/study/sub-01/scan.nii      | may     |
      | qa-bucket/study/sub-03/scan.nii      | may not |
      | qa-bucket/study/sub-03/later/new.nii | may not |
      | qa-bucket/study/sub-03/              | may not |
      | qa-bucket/study/notes.txt            | may not |
      | qa-bucket/study/notes.txt.bak        | may     |

  @AC-10
  Scenario Outline: An excluded folder isn't shown unless something else shows it
    Given the user holds "read" on "qa-bucket/study/*" leaving out "qa-bucket/study/sub-03/*"
    Then the folder "<folder>" is <shown> when browsing to "read"

    Examples:
      | folder                    | shown     |
      | qa-bucket/study/          | shown     |
      | qa-bucket/study/sub-01/   | shown     |
      | qa-bucket/study/sub-03/   | not shown |
      | qa-bucket/study/sub-03/a/ | not shown |

  @AC-10
  Scenario: Another policy can still give what one policy leaves out
    Given the user holds "read" on "qa-bucket/study/*" leaving out "qa-bucket/study/sub-03/*"
    And the user holds "read" on "qa-bucket/study/sub-03/scan.nii"
    Then the user may "read" "qa-bucket/study/sub-03/scan.nii"
    And the folder "qa-bucket/study/sub-03/" is shown when browsing to "read"
    And the user may not "read" "qa-bucket/study/sub-03/other.nii"

  @AC-10
  Scenario Outline: Only paths inside a folder policy can be left out
    When an administrator saves a policy on "<policy>" leaving out "<excluded>"
    Then it is <outcome>

    Examples:
      | policy            | excluded                    | outcome                                  |
      | qa-bucket/study/* | qa-bucket/study/sub-03/*    | saved leaving out qa-bucket/study/sub-03/* |
      | *                 | qa-bucket/study/*           | saved leaving out qa-bucket/study/*      |
      | qa-bucket/study/* | qa-bucket/other/*           | refused                                  |
      | qa-bucket/study/* | qa-bucket/study/*           | refused                                  |
      | qa-bucket/a.txt   | qa-bucket/a.txt             | refused                                  |
      | qa-bucket/study/* | qa-bucket/study/sub-0*/x    | refused                                  |

  @AC-6
  Scenario Outline: A folder policy limited to file endings covers only those files
    Given the user holds "read" on "qa-bucket/study/*" for files ending in ".nii, .nii.gz"
    Then the user <may> "read" "<path>"

    Examples:
      | path                              | may     |
      | qa-bucket/study/sub-01/scan.nii   | may     |
      | qa-bucket/study/sub-01/SCAN.NII   | may     |
      | qa-bucket/study/sub-01/scan.nii.gz| may     |
      | qa-bucket/study/sub-01/notes.txt  | may not |
      | qa-bucket/study/sub-01/scan.nii.bak | may not |
      | qa-bucket/other/scan.nii          | may not |
      | qa-bucket/study/sub-01/           | may     |

  @AC-6
  Scenario: Endings and exclusions apply together
    Given the user holds "read" on "qa-bucket/study/*" for files ending in ".nii" leaving out "qa-bucket/study/sub-03/*"
    Then the user may "read" "qa-bucket/study/sub-01/scan.nii"
    And the user may not "read" "qa-bucket/study/sub-03/scan.nii"
    And the user may not "read" "qa-bucket/study/sub-01/notes.txt"

  @AC-6
  Scenario Outline: Endings are checked when a policy is saved
    When an administrator saves a policy on "<policy>" for files ending in "<endings>"
    Then it is <outcome>

    Examples:
      | policy            | endings      | outcome                          |
      | qa-bucket/study/* | .NII, .nii.gz | saved for endings .nii, .nii.gz |
      | qa-bucket/a.txt   | .txt         | refused                          |
      | qa-bucket/study/* | nii          | refused                          |
      | qa-bucket/study/* | .n*i         | refused                          |
      | qa-bucket/study/* | ./x          | refused                          |
