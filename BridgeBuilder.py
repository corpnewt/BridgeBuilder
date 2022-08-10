from Scripts import *
import os, re

class BridgeBuilder:
    def __init__(self, **kwargs):
        self.dl = downloader.Downloader()
        self.u  = utils.Utils("Bridge Builder")
        self.r  = run.Run()
        try:
            self.d = dsdt.DSDT()
        except Exception as e:
            print("Something went wrong :( - Aborting!\n - {}".format(e))
            exit(1)
        self.dsdt = None
        self.scripts = "Scripts"
        self.output = "Results"

    def select_dsdt(self):
        self.u.head("Select DSDT")
        print(" ")
        print("M. Main")
        print("Q. Quit")
        print(" ")
        dsdt = self.u.grab("Please drag and drop a DSDT.aml or origin folder here:  ")
        if dsdt.lower() == "m":
            return self.dsdt
        if dsdt.lower() == "q":
            self.u.custom_quit()
        out = self.u.check_path(dsdt)
        if out:
            if self.d.load(out):
                return out
        return self.select_dsdt()

    def ensure_dsdt(self):
        if self.dsdt and self.d.dsdt:
            # Got it already
            return True
        # Need to prompt
        self.dsdt = self.select_dsdt()
        if self.dsdt and self.d.dsdt:
            return True
        return False

    def write_ssdt(self, ssdt_name, ssdt):
        res = self.d.check_output(self.output)
        dsl_path = os.path.join(res,ssdt_name+".dsl")
        aml_path = os.path.join(res,ssdt_name+".aml")
        iasl_path = self.d.iasl
        with open(dsl_path,"w") as f:
            f.write(ssdt)
        print("Compiling...")
        out = self.r.run({"args":[iasl_path, dsl_path]})
        if out[2] != 0:
            print(" - {}".format(out[1]))
            self.re.reveal(dsl_path,True)
            return False
        return True

    def get_address_from_line(self, line):
        try:
            return int(self.d.dsdt_lines[line].split("_ADR, ")[1].split(")")[0].replace("Zero","0x0").replace("One","0x1"),16)
        except:
            return None

    def hexy(self,integer):
        return "0x"+hex(integer)[2:].upper()

    def get_bridge_devices(self, path):
        # Takes a Pci(x,x)/Pci(x,x) style path, and returns named bridges and addresses
        adrs = re.split(r"#|\/",path.lower().replace("pciroot(","").replace("pci(","").replace(")",""))
        # Walk the addresses and create our bridge objects
        bridges = []
        for bridge in adrs:
            if not len(bridge): continue # Skip empty entries
            if not "," in bridge: return # Uh... we don't want to bridge the PciRoot - something's wrong.
            try:
                adr1,adr2 = [int(x,16) for x in bridge.split(",")]
                # Join the addresses as a 32-bit int
                adr_int = (adr1 << 16) + adr2
                adr = {0:"Zero",1:"One"}.get(adr_int,"0x"+hex(adr_int).upper()[2:].rjust(8 if adr1 > 0 else 0,"0"))
                brg_num = str(hex(len(bridges))[2:].upper())
                name = "BRG0"[:-len(brg_num)]+brg_num
                bridges.append((name,adr))
            except:
                return [] # Failed :(
        return bridges

    def sanitize_device_path(self, device_path):
        # Walk the device_path, gather the addresses, and rebuild it
        if not device_path.lower().startswith("pciroot("):
            # Not a device path - bail
            return
        # Strip out PciRoot() and Pci() - then split by separators
        adrs = re.split(r"#|\/",device_path.lower().replace("pciroot(","").replace("pci(","").replace(")",""))
        new_path = []
        for i,adr in enumerate(adrs):
            if i == 0:
                # Check for roots
                if "," in adr: return # Broken
                try: new_path.append("PciRoot({})".format(self.hexy(int(adr,16))))
                except: return # Broken again :(
            else:
                if "," in adr: # Not Windows formatted
                    try: adr1,adr2 = [int(x,16) for x in adr.split(",")]
                    except: return # REEEEEEEEEE
                else:
                    try:
                        adr = int(adr,16)
                        adr2,adr1 = adr & 0xFF, adr >> 8 & 0xFF
                    except: return # AAAUUUGGGHHHHHHHH
                # Should have adr1 and adr2 - let's add them
                new_path.append("Pci({},{})".format(self.hexy(adr1),self.hexy(adr2)))
        return "/".join(new_path)

    def get_longest_match(self, device_dict, match_path):
        longest = 0
        matched = None
        exact   = False
        for device in device_dict:
            if match_path.lower().startswith(device_dict[device].lower()) and len(device_dict[device])>longest:
                # Got a longer match - set it
                matched = device
                longest = len(device_dict[device])
                # Check if it's an exact match, and bail early
                if device_dict[device].lower() == match_path.lower():
                    exact = True
                    break
        return (matched,device_dict[matched],exact,longest)

    def generate_ssdt(self,scope,bridges):
        # Let's create an SSDT that sets up our PCI bridges
        ssdt = """// Source and info from:
// https://github.com/acidanthera/OpenCorePkg/blob/master/Docs/AcpiSamples/Source/SSDT-BRG0.dsl
DefinitionBlock ("", "SSDT", 2, "CORP", "PCIBRG", 0x00000000)
{
    External ([[scope]], DeviceObj)
    Scope ([[scope]])
    {
""".replace("[[scope]]",scope)
        ssdt_end = """    }
}
"""
        # Let's iterate our bridges
        pc = "    " # Pad char
        for i,bridge in enumerate(bridges,start=2):
            if i-1==len(bridges):
                ssdt += pc*i + "// Customize this device name if needed, eg. GFX0\n"
                ssdt += pc*i + "Device (PXSX)\n"
            else:
                ssdt += pc*i + "Device ({})\n".format(bridge[0])
            ssdt += pc*i + "{\n"
            ssdt += pc*(i+1) + "Name (_ADR, {})\n".format(bridge[1])
            ssdt_end = pc*i + "}\n" + ssdt_end
        ssdt += ssdt_end
        return ssdt

    def get_device_path(self):
        while True:
            self.u.head("Input Device Path")
            print("")
            print("A valid device path will have one of the following formats:")
            print("")
            print("macOS:   PciRoot(0x0)/Pci(0x0,0x0)/Pci(0x0,0x0)")
            print("Windows: PCIROOT(0)#PCI(0000)#PCI(0000)")
            print("")
            print("M. Main")
            print("Q. Quit")
            print(" ")
            path = self.u.grab("Please enter the device path needing bridges:  ")
            if path.lower() == "m":
                return
            if path.lower() == "q":
                self.u.custom_quit()
            path = self.sanitize_device_path(path)
            if not path: continue
            return path

    def gen_bridges(self):
        if not self.ensure_dsdt(): return
        test_path = self.get_device_path()
        if not test_path: return
        self.u.head("Building Bridges")
        print("")
        print("Gathering ACPI devices...")
        # Let's gather our roots - and any other paths that and in _ADR
        pci_roots = self.d.get_device_paths_with_hid(hid="PNP0A08")
        paths = self.d.get_path_of_type(obj_type="Name",obj="_ADR")
        # Let's create our dictionary device paths - starting with the roots
        print("Generating device paths...")
        device_dict = {}
        for path in pci_roots:
            device_adr = self.d.get_name_paths(obj=path[0]+"._ADR")
            if device_adr and len(device_adr)==1:
                adr = self.get_address_from_line(device_adr[0][1])
                device_dict[path[0]] = "PciRoot({})".format(self.hexy(adr))
        # First - let's create a new list of tuples with the ._ADR stripped
        # The goal here is to ensure pathing is listed in the proper order.
        sanitized_paths = sorted([(x[0][0:-5],x[1],x[2]) for x in paths])
        for path in sanitized_paths:
            adr = self.get_address_from_line(path[1])
            # Let's bitshift to get both addresses
            try:
                adr2,adr1 = adr & 0xFFFF, adr >> 16 & 0xFFFF
            except:
                continue # Bad address?
            # Let's check if our path already exists
            if path[0] in device_dict: continue # Skip
            # Doesn't exist - let's see if the parent path does?
            parent = ".".join(path[0].split(".")[:-1])
            if not parent in device_dict: continue # No parent either - bail...
            # Our parent path exists - let's copy its device_path, and append our addressing
            device_path = device_dict[parent]
            if not device_path: continue # Bail - no device_path set
            device_path += "/Pci({},{})".format(self.hexy(adr1),self.hexy(adr2))
            device_dict[path[0]] = device_path

        print("Matching against {}".format(test_path))
        match = self.get_longest_match(device_dict,test_path)
        if not match:
            print(" - No matches found!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        if match[2]:
            print(" - No bridge needed!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        # We got a match - and need bridges
        print("Matched {} - {}".format(match[0],match[1]))
        print("Generating bridges for {}...".format(test_path[match[-1]+1:]))
        bridges = self.get_bridge_devices(test_path[match[-1]+1:])
        if not bridges:
            print(" - Something went wrong!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        print("Generating SSDT...")
        ssdt = self.generate_ssdt(match[0],bridges)
        if not self.write_ssdt("SSDT-PCIBRG",ssdt):
            print(" - Something went wrong!")
            print("")
            self.u.grab("Press [enter] to return...")
            return
        print("SSDT-PCIBRG.dsl|.aml saved to: {}".format(self.d.check_output(self.output)))
        print("")
        print("Done.")
        print("")
        self.u.grab("Press [enter] to return...")

    def main(self):
        cwd = os.getcwd()
        self.u.head()
        print("")
        print("Current DSDT:  {}".format(self.dsdt))
        print("")
        print("B. Generate PCI Bridges")
        print("D. Select DSDT or origin folder")
        print("Q. Quit")
        print("")
        menu = self.u.grab("Please make a selection:  ")
        if not len(menu):
            return
        if menu.lower() == "q":
            self.u.custom_quit()
        if menu.lower() == "d":
            self.dsdt = self.select_dsdt()
            return
        if menu.lower() == "b":
            self.gen_bridges()
        return

if __name__ == '__main__':
    if 2/3 == 0: input = raw_input
    b = BridgeBuilder()
    while True:
        try:
            b.main()
        except Exception as e:
            print("An error occurred: {}".format(e))
            input("Press [enter] to continue...")
