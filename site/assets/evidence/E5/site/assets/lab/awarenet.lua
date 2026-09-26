-- AwareNet application framing over ordinary TCP: uint8 + uint32 + uint32.
-- This dissector does not modify TCP. Restricted to the lab port 20500.
local proto = Proto("awarenet", "AwareNet byte transport")
local kind = ProtoField.uint8("awarenet.kind", "Kind", base.DEC)
local tid = ProtoField.string("awarenet.tid", "Transfer ID")
local cid = ProtoField.string("awarenet.cid", "Client ID")
local seq = ProtoField.uint32("awarenet.seq", "Chunk sequence", base.DEC)
local off = ProtoField.uint32("awarenet.offset", "Byte offset", base.DEC)
local bytes = ProtoField.uint32("awarenet.bytes", "Payload bytes", base.DEC)
local metadata = ProtoField.string("awarenet.metadata", "Metadata JSON")
local fin = ProtoField.bool("awarenet.fin", "Tensor FIN")
local ack = ProtoField.bool("awarenet.ack", "Tensor ACK")
proto.fields = {kind, tid, cid, seq, off, bytes, metadata, fin, ack}

function proto.dissector(buf, pinfo, tree)
    local offset = 0
    while offset < buf:len() do
        if buf:len()-offset < 9 then
            pinfo.desegment_offset = offset
            pinfo.desegment_len = 9-(buf:len()-offset)
            return
        end
        local ml = buf(offset+1,4):uint()
        local pl = buf(offset+5,4):uint()
        if ml > 1048576 or pl > 16777216 then return 0 end
        local total = 9+ml+pl
        if buf:len()-offset < total then
            pinfo.desegment_offset = offset
            pinfo.desegment_len = total-(buf:len()-offset)
            return
        end
        pinfo.cols.protocol = "AWARENET"
        local text = buf(offset+9,ml):string()
        local sub = tree:add(proto,buf(offset,total))
        sub:add(kind,buf(offset,1))
        sub:add(bytes,buf(offset+5,4))
        sub:add(metadata,text)
        for _, item in ipairs({{tid,"tid"},{cid,"cid"}}) do
            local value = text:match('"'..item[2]..'"%s*:%s*"([^"\\]*)"')
            if value then sub:add(item[1],value) end
        end
        for _, item in ipairs({{seq,"seq"},{off,"off"}}) do
            local value = text:match('"'..item[2]..'"%s*:%s*(%d+)')
            if value then sub:add(item[1],tonumber(value)) end
        end
        sub:add(fin,text:match('"fin"%s*:%s*1') ~= nil)
        sub:add(ack,text:match('"ack"%s*:%s*1') ~= nil)
        offset = offset+total
    end
end
DissectorTable.get("tcp.port"):add(20500,proto)
