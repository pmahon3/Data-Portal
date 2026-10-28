-- Pandoc filter for the PDF copies of the docs (see build-pdf.sh).
-- Links to a doc that has a PDF copy point to that PDF; requirement IDs
-- (PX-n) become link targets in their register and links everywhere else.

local REGISTER = "posix-storage"
local has_pdf = { ["access-control"] = true, ["posix-storage"] = true }

local input = PANDOC_STATE.input_files[1] or ""
local in_register = input:match("([^/]+)%.md$") == REGISTER
local dir = input:match("^(.*)/[^/]+$") or "."
local register_pdf = dir:match("requirements$") and (REGISTER .. ".pdf")
  or ("../requirements/" .. REGISTER .. ".pdf")

function Link(el)
  local path, name, frag = el.target:match("^(.-)([^/]+)%.md(#?.*)$")
  if name and has_pdf[name] and not el.target:match("^%a+://") then
    el.target = path .. name .. ".pdf" .. frag
  end
  return el
end

local function id_link(id)
  if in_register then
    return pandoc.RawInline("latex", "\\hyperlink{" .. id .. "}{" .. id .. "}")
  end
  return pandoc.Link(id, register_pdf .. "#" .. id)
end

-- Split "(PX-8;" into "(", link, ";".
local function linkify(s)
  local pre, id, post = s:match("^(.-)(PX%-%d+)(.*)$")
  if not id then return nil end
  return { pandoc.Str(pre), id_link(id), pandoc.Str(post) }
end

function Table(tbl)
  if not in_register then return nil end
  -- First cell of each body row: make the ID a target, not a link.
  for _, body in ipairs(tbl.bodies) do
    for _, row in ipairs(body.body) do
      local cell = row.cells[1]
      local text = pandoc.utils.stringify(cell.contents)
      if text:match("^PX%-%d+$") then
        -- A named target, so links from this PDF and from other PDFs land on the row.
        local raw = "\\leavevmode\\hypertarget{" .. text .. "}{}" .. text
        cell.contents = { pandoc.Plain({ pandoc.RawInline("latex", raw) }) }
      end
    end
  end
  return tbl
end

function Inlines(inlines)
  local out = pandoc.Inlines({})
  for _, el in ipairs(inlines) do
    local parts = el.t == "Str" and linkify(el.text)
    if parts then out:extend(parts) else out:insert(el) end
  end
  return out
end

-- Tables first, so their ID cells become targets before IDs elsewhere become links.
return { { Table = Table }, { Link = Link, Inlines = Inlines } }
