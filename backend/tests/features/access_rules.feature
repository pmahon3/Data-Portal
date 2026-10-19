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
