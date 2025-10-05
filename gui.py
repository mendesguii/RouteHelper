import os
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledText
from tkinter import filedialog, messagebox, simpledialog
from main import RouteHelper


AIRCRAFT_OPTIONS = ["A319", "A320", "A321", "B738_ZIBO", "B738", "B737"]
DEFAULT_FL = "330"
MIN_WINDOW_SIZE = (1200, 700)
THEME_DARK = "cyborg"
THEME_LIGHT = "flatly"


class RouteHelperGUI:
    """Main GUI class for RouteHelper."""
    def __init__(self, root):
        self.root = root
        self.root.title("🛫 RouteHelper GUI 🛬")
        self.root.minsize(*MIN_WINDOW_SIZE)
        self.helper = RouteHelper()
        self.current_theme = THEME_DARK
        self._setup_menu()
        self._setup_tabs()
        os.makedirs('flights', exist_ok=True)

    def _setup_menu(self):
        """Setup the menu bar."""
        menubar = tb.Menu(self.root)
        self.root.config(menu=menubar)
        view_menu = tb.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu, underline=0)
        view_menu.add_command(label="Toggle Dark Mode", command=self.toggle_dark_mode, accelerator="Alt+D")
        self.root.bind_all('<Alt-d>', lambda event: self.toggle_dark_mode())
        settings_menu = tb.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settings_menu, underline=0)
        settings_menu.add_command(label="Set Data Folder...", command=self.set_data_folder)
        settings_menu.add_command(label="Set AIRAC Cycle...", command=self.set_airac_cycle)

    def _setup_tabs(self):
        """Setup the main tabs."""
        top_frame = tb.Frame(self.root)
        top_frame.pack(fill='x', padx=10, pady=(10, 0))
        tab_control = tb.Notebook(top_frame, bootstyle="primary")
        tab_control.pack(side='left', fill='both', expand=True)

        # Combined Procedures + METAR tab
        self.procmetar_tab = tb.Frame(tab_control)
        tab_control.add(self.procmetar_tab, text='🗺️ Procedures/🌦️ METAR')

        # Route Planner tab
        self.route_tab = tb.Frame(tab_control)
        tab_control.add(self.route_tab, text='🛣️ Route Planner')

        # Build contents
        self._create_proc_metar_tab()
        self._create_route_tab()

        for tab in (self.procmetar_tab, self.route_tab):
            tab.grid_rowconfigure(0, weight=1)
            tab.grid_columnconfigure(0, weight=1)

    def _create_proc_metar_tab(self):
        """Create a combined tab with SID/STAR and METAR sections stacked vertically."""
        frame = self.procmetar_tab

        # Procedures section
        proc_group = tb.Labelframe(frame, text="🗺️ SID/STAR", bootstyle="primary")
        proc_group.grid(row=0, column=0, sticky='nsew', padx=6, pady=(6, 3))
        proc_group.grid_columnconfigure(0, weight=1)
        # Controls row
        self.proc_icao = self._add_entry(proc_group, 0, 1, width=10, label="ICAO:", label_col=0)
        self.proc_type = self._add_combobox(proc_group, 0, 3, ["SID", "STAR"], width=8, label="📄 Type:", label_col=2)
        self.proc_type.current(0)
        self.proc_fix = self._add_entry(proc_group, 0, 5, width=12, label="🧭 Fix (optional):", label_col=4)
        tb.Button(proc_group, text="🔍 Search", bootstyle="primary", command=self.proc_search).grid(row=0, column=6, padx=5)
        self.proc_output = self._add_scrolled_text(proc_group, 1, 0, colspan=7, width=90, height=12)
        proc_group.grid_rowconfigure(1, weight=1)

        # METAR section
        metar_group = tb.Labelframe(frame, text="🌦️ METAR", bootstyle="success")
        metar_group.grid(row=1, column=0, sticky='nsew', padx=6, pady=(3, 6))
        metar_group.grid_columnconfigure(0, weight=1)
        self.metar_icao = self._add_entry(metar_group, 0, 1, width=10, label="🛬 ICAO:", label_col=0)
        tb.Button(metar_group, text="🌦️ Get METAR", bootstyle="primary", command=self.metar_search).grid(row=0, column=2, padx=5)
        self.metar_output = self._add_scrolled_text(metar_group, 1, 0, colspan=3, width=90, height=12)
        metar_group.grid_rowconfigure(1, weight=1)

    def set_data_folder(self):
        """Allow user to set the data folder and update .env."""
        folder = filedialog.askdirectory(title="Select Data Folder")
        if folder:
            env_path = os.path.join(os.getcwd(), '.env')
            lines = []
            found = False
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    for line in f:
                        if line.strip().startswith('DATA_PATH='):
                            lines.append(f'DATA_PATH={folder}\n')
                            found = True
                        else:
                            lines.append(line)
            if not found:
                lines.append(f'DATA_PATH={folder}\n')
            with open(env_path, 'w') as f:
                f.writelines(lines)
            messagebox.showinfo("Data Folder", f"Data folder set to: {folder}\nRestart app to apply.")

    def toggle_dark_mode(self):
        """Toggle between dark and light mode."""
        new_theme = THEME_DARK if self.current_theme == THEME_LIGHT else THEME_LIGHT
        self.root.style.theme_use(new_theme)
        self.current_theme = new_theme

    def _create_proc_tab(self):
        """Create SID/STAR tab widgets."""
        frame = self.proc_tab
        self.proc_icao = self._add_entry(frame, 0, 1, width=10, label="�️ ICAO:", label_col=0)
        self.proc_type = self._add_combobox(frame, 0, 3, ["SID", "STAR"], width=8, label="📄 Type:", label_col=2)
        self.proc_type.current(0)
        self.proc_fix = self._add_entry(frame, 0, 5, width=12, label="🧭 Fix (optional):", label_col=4)
        tb.Button(frame, text="🔍 Search", bootstyle="primary", command=self.proc_search).grid(row=0, column=6, padx=5)
        self.proc_output = self._add_scrolled_text(frame, 1, 0, colspan=7, width=90, height=20)

    def proc_search(self):
        icao = self.proc_icao.get().strip().upper()
        proc_type = self.proc_type.get()
        fix = self.proc_fix.get().strip().upper()
        self.proc_output.delete('1.0', 'end')
        if not icao:
            self.proc_output.insert('end', "Please enter an ICAO code.")
            return
        try:
            self.helper.get_file_data(f'{self.helper.data_path}/{icao}.dat')
            if proc_type == "SID":
                if fix:
                    self.helper.plan = ''
                    self.helper.search_in_dict(self.helper.structure_data(self.helper.sids), fix)
                    self.proc_output.insert('end', (self.helper.plan or "No results found.").rstrip())
                else:
                    result = self.helper.structure_data(self.helper.sids)
                    self.proc_output.insert('end', str(result).rstrip())
            elif proc_type == "STAR":
                if fix:
                    self.helper.plan = ''
                    self.helper.search_in_dict(self.helper.structure_data(self.helper.stars), fix)
                    self.proc_output.insert('end', (self.helper.plan or "No results found.").rstrip())
                else:
                    result = self.helper.structure_data(self.helper.stars)
                    self.proc_output.insert('end', str(result).rstrip())
        except Exception as e:
            self.proc_output.insert('end', f"Error: {e}")

    def _create_metar_tab(self):
        """Create METAR tab widgets."""
        frame = self.metar_tab
        self.metar_icao = self._add_entry(frame, 0, 1, width=10, label="🛬 ICAO:", label_col=0)
        tb.Button(frame, text="🌦️ Get METAR", bootstyle="primary", command=self.metar_search).grid(row=0, column=2, padx=5)
        self.metar_output = self._add_scrolled_text(frame, 1, 0, colspan=3, width=90, height=20)

    def metar_search(self):
        icao = self.metar_icao.get().strip().upper()
        self.metar_output.delete('1.0', 'end')
        if not icao:
            self.metar_output.insert('end', "Please enter an ICAO code.")
            return
        try:
            self.helper.plan = ''
            self.helper.get_metar(icao)
            self.metar_output.insert('end', (self.helper.plan or "No METAR found.").rstrip())
        except Exception as e:
            self.metar_output.insert('end', f"Error: {e}")

    def _create_route_tab(self):
        """Create Route Planner tab widgets and layout."""
        frame = self.route_tab
        # Input row
        self.route_origin = self._add_entry(frame, 0, 1, width=10, label="🛫 Origin ICAO:", label_col=0, sticky='ew', padx=(0,2), pady=2)
        self.route_dest = self._add_entry(frame, 0, 3, width=10, label="🛬 Destination ICAO:", label_col=2, sticky='ew', padx=(0,2), pady=2)
        self.route_plane = self._add_combobox(frame, 0, 5, AIRCRAFT_OPTIONS, width=12, label="✈️ Aircraft:", label_col=4, sticky='ew', padx=(0,2), pady=2)
        self.route_plane.configure(state="normal")
        self.fl_start = self._add_entry(frame, 0, 7, width=5, label="FL Start:", label_col=6, sticky='ew', padx=(0,2), pady=2)
        self.fl_start.insert(0, DEFAULT_FL)
        self.fl_end = self._add_entry(frame, 0, 9, width=5, label="FL End:", label_col=8, sticky='ew', padx=(0,2), pady=2)
        self.fl_end.insert(0, DEFAULT_FL)
        tb.Button(frame, text="🗺️ Plan Route", bootstyle="primary", command=self.route_search).grid(row=0, column=10, padx=(2,2), pady=2, sticky='ew')
        tb.Button(frame, text="📝 Generate IVAO FPL", bootstyle="info-outline", command=self.generate_ivao_fpl).grid(row=0, column=11, padx=(2,2), pady=2, sticky='ew')
        # Set column weights for proper resizing
        for i in range(12):
            frame.grid_columnconfigure(i, weight=2 if i in [1,3,5,7,9] else (0 if i in [0,2,4,6,8] else 1))
        # Layout frames
        loadsheet_frame = tb.Labelframe(frame, text="📋 Loadsheet", bootstyle="info")
        routefixes_frame = tb.Labelframe(frame, text="🚦 Route & Fixes", bootstyle="primary")
        metar_frame = tb.Labelframe(frame, text="🌦️ METAR", bootstyle="success")
        loadsheet_frame.grid(row=1, column=0, columnspan=6, sticky='nsew', padx=5, pady=(5,2))
        routefixes_frame.grid(row=1, column=6, columnspan=6, sticky='nsew', padx=5, pady=(5,2))
        metar_frame.grid(row=2, column=0, columnspan=12, sticky='nsew', padx=5, pady=(2,5))
        for i in range(12):
            frame.grid_columnconfigure(i, weight=1)
        frame.grid_rowconfigure(1, weight=2)
        frame.grid_rowconfigure(2, weight=1)
        loadsheet_frame.grid_rowconfigure(0, weight=1)
        loadsheet_frame.grid_columnconfigure(0, weight=1)
        routefixes_frame.grid_rowconfigure(0, weight=1)
        routefixes_frame.grid_columnconfigure(0, weight=1)
        metar_frame.grid_rowconfigure(0, weight=1)
        metar_frame.grid_columnconfigure(0, weight=1)
        # METAR subdivisions (side by side)
        metar_origin_frame = tb.Labelframe(metar_frame, text="🛫 Origin", bootstyle="success")
        metar_dest_frame = tb.Labelframe(metar_frame, text="🛬 Destination", bootstyle="success")
        metar_origin_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        metar_dest_frame.grid(row=0, column=1, sticky='nsew', padx=2, pady=2)
        metar_frame.grid_rowconfigure(0, weight=1)
        metar_frame.grid_columnconfigure(0, weight=1)
        metar_frame.grid_columnconfigure(1, weight=1)
        self.route_metar_origin_output = self._add_scrolled_text(metar_origin_frame, 0, 0, width=45, height=5)
        self.route_metar_dest_output = self._add_scrolled_text(metar_dest_frame, 0, 0, width=45, height=5)
        tb.Button(metar_origin_frame, text="🔄 Update", bootstyle="success-outline", command=self.update_metar_origin).grid(row=1, column=0, sticky='e', pady=2)
        tb.Button(metar_dest_frame, text="🔄 Update", bootstyle="success-outline", command=self.update_metar_dest).grid(row=1, column=0, sticky='e', pady=2)
        # Ensure text areas fill their containers
        metar_origin_frame.grid_rowconfigure(0, weight=1)
        metar_origin_frame.grid_columnconfigure(0, weight=1)
        metar_dest_frame.grid_rowconfigure(0, weight=1)
        metar_dest_frame.grid_columnconfigure(0, weight=1)
        # Route & Fixes subdivisions
        route_route_frame = tb.Labelframe(routefixes_frame, text="🗺️ Route", bootstyle="primary")
        sid_frame = tb.Labelframe(routefixes_frame, text="🛫 SID Fix Search", bootstyle="primary")
        star_frame = tb.Labelframe(routefixes_frame, text="🛬 STAR Fix Search", bootstyle="primary")
        route_route_frame.grid(row=0, column=0, sticky='nsew', padx=2, pady=2)
        sid_frame.grid(row=1, column=0, sticky='nsew', padx=2, pady=2)
        star_frame.grid(row=2, column=0, sticky='nsew', padx=2, pady=2)
        routefixes_frame.grid_rowconfigure(0, weight=1)
        routefixes_frame.grid_rowconfigure(1, weight=1)
        routefixes_frame.grid_rowconfigure(2, weight=1)
        routefixes_frame.grid_columnconfigure(0, weight=1)
        self.route_route_output = self._add_scrolled_text(route_route_frame, 0, 0, width=50, height=8)
        route_route_frame.grid_rowconfigure(0, weight=1)
        route_route_frame.grid_columnconfigure(0, weight=1)
        self.sid_fix_entry = self._add_entry(sid_frame, 0, 0, width=20, sticky='w', padx=2)
        tb.Button(sid_frame, text="🔍 Search", bootstyle="primary-outline", command=self.search_sid_fix).grid(row=0, column=1, padx=2)
        self.sid_fix_output = self._add_scrolled_text(sid_frame, 1, 0, colspan=2, width=60, height=8)
        sid_frame.grid_rowconfigure(1, weight=1)
        sid_frame.grid_columnconfigure(0, weight=1)
        sid_frame.grid_columnconfigure(1, weight=1)
        self.star_fix_entry = self._add_entry(star_frame, 0, 0, width=20, sticky='w', padx=2)
        tb.Button(star_frame, text="🔍 Search", bootstyle="primary-outline", command=self.search_star_fix).grid(row=0, column=1, padx=2)
        self.star_fix_output = self._add_scrolled_text(star_frame, 1, 0, colspan=2, width=60, height=8)
        star_frame.grid_rowconfigure(1, weight=1)
        star_frame.grid_columnconfigure(0, weight=1)
        star_frame.grid_columnconfigure(1, weight=1)
        # Loadsheet output
        self.route_loadsheet_output = self._add_scrolled_text(loadsheet_frame, 0, 0, width=40, height=22)

    # --- Helper widget methods ---
    def _add_label(self, parent, row, col, text, **kwargs):
        lbl = tb.Label(parent, text=text)
        lbl.grid(row=row, column=col, **kwargs)
        return lbl

    def _add_entry(self, parent, row, col, width=10, label=None, label_col=None, **kwargs):
        if label is not None and label_col is not None:
            self._add_label(parent, row, label_col, label, sticky='e')
        entry = tb.Entry(parent, width=width)
        entry.grid(row=row, column=col, **kwargs)
        return entry

    def _add_combobox(self, parent, row, col, values, width=10, label=None, label_col=None, **kwargs):
        if label is not None and label_col is not None:
            self._add_label(parent, row, label_col, label, sticky='e')
        cb = tb.Combobox(parent, values=values, width=width)
        cb.grid(row=row, column=col, **kwargs)
        return cb

    def _add_scrolled_text(self, parent, row, col, colspan=1, width=40, height=10, **kwargs):
        st = ScrolledText(parent, width=width, height=height, autohide=True)
        st.grid(row=row, column=col, columnspan=colspan, sticky='nsew', **kwargs)
        return st

    def set_airac_cycle(self):
        """Prompt for AIRAC cycle and save to .env; update helper."""
        val = simpledialog.askinteger("Set AIRAC Cycle", "Enter AIRAC cycle (e.g., 2501):", minvalue=1000, maxvalue=9999)
        if val is None:
            return
        env_path = os.path.join(os.getcwd(), '.env')
        lines = []
        found = False
        if os.path.exists(env_path):
            with open(env_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('CYCLE='):
                        lines.append(f'CYCLE={val}\n')
                        found = True
                    else:
                        lines.append(line)
        if not found:
            lines.append(f'CYCLE={val}\n')
        with open(env_path, 'w') as f:
            f.writelines(lines)
        try:
            self.helper.cycle = int(val)
        except Exception:
            self.helper.cycle = val
        messagebox.showinfo("AIRAC Cycle", f"AIRAC cycle set to: {val}")

    def generate_ivao_fpl(self):
        import os
        from tkinter import messagebox
        origin = self.route_origin.get().strip().upper()
        dest = self.route_dest.get().strip().upper()
        plane = self.route_plane.get().strip().upper()
        if not origin or not dest or not plane:
            messagebox.showerror("Error", "Please enter all fields before generating IVAO FPL.")
            return
        # Ensure route is generated
        route_str = self.route_route_output.get('1.0', 'end').strip()
        if not route_str or route_str.startswith("No route"):
            messagebox.showerror("Error", "No route generated to save.")
            return
        # Use RouteHelper's gen_flight_plan to generate the .fpl file in flights folder
        flights_dir = os.path.join(os.getcwd(), 'flights')
        os.makedirs(flights_dir, exist_ok=True)
        self.helper.gen_flight_plan(origin, dest, plane, output_dir=flights_dir)
        # Rename to an IVAO-friendly filename
        src = os.path.join(flights_dir, f'{origin}{dest}.fpl')
        dst = os.path.join(flights_dir, f'{origin}_{dest}_{plane}_ivao.fpl')
        if os.path.exists(src):
            try:
                os.replace(src, dst)
            except Exception:
                # Fallback to copy+remove if replace fails on some FS
                import shutil
                shutil.copyfile(src, dst)
                os.remove(src)
        else:
            dst = src  # Unexpected, but show the original path
        messagebox.showinfo("IVAO FPL", f"IVAO FPL saved to {dst}")

    def route_search(self):
        origin = self.route_origin.get().strip().upper()
        dest = self.route_dest.get().strip().upper()
        plane = self.route_plane.get().strip().upper()
        # Clear all outputs
        self.route_loadsheet_output.delete('1.0', 'end')
        self.route_route_output.delete('1.0', 'end')
        self.sid_fix_output.delete('1.0', 'end')
        self.star_fix_output.delete('1.0', 'end')
        self.route_metar_origin_output.delete('1.0', 'end')
        self.route_metar_dest_output.delete('1.0', 'end')
        if not origin or not dest or not plane:
            self.route_loadsheet_output.insert('end', "Please enter all fields.")
            return
        try:
            # Loadsheet
            self.helper.get_fuel(origin, dest, plane)
            loadsheet = self.helper.plan or "No loadsheet generated."
            self.route_loadsheet_output.insert('end', str(loadsheet).rstrip())

            # Route
            minalt = (self.fl_start.get() or DEFAULT_FL)
            maxalt = (self.fl_end.get() or DEFAULT_FL)
            self.helper.get_route(origin, dest, minalt, maxalt, getattr(self.helper, 'cycle', 2501))
            # Print route as a single string (not a list)
            if self.helper.route:
                if isinstance(self.helper.route, list):
                    route_text = ' '.join(str(x) for x in self.helper.route)
                else:
                    route_text = str(self.helper.route)
            else:
                route_text = "No route generated."
            self.route_route_output.insert('end', route_text.rstrip())

            # SID Fixes (origin)
            self.helper.get_file_data(f'{self.helper.data_path}/{origin}.dat')
            if self.helper.route:
                self.helper.plan = ''
                self.helper.search_in_dict(self.helper.structure_data(self.helper.sids), self.helper.route[0])
                self.sid_fix_output.insert('end', (self.helper.plan or "No SID fix found.").rstrip())
            else:
                self.sid_fix_output.insert('end', "No SID fix found.")

            # STAR Fixes (destination)
            self.helper.get_file_data(f'{self.helper.data_path}/{dest}.dat')
            if self.helper.route:
                self.helper.plan = ''
                self.helper.search_in_dict(self.helper.structure_data(self.helper.stars), self.helper.route[-1])
                self.star_fix_output.insert('end', (self.helper.plan or "No STAR fix found.").rstrip())
            else:
                self.star_fix_output.insert('end', "No STAR fix found.")

            # METAR
            self.helper.plan = ''
            self.helper.get_metar(origin)
            self.route_metar_origin_output.insert('end', (self.helper.plan or "No METAR found.").rstrip())
            self.helper.plan = ''
            self.helper.get_metar(dest)
            self.route_metar_dest_output.insert('end', (self.helper.plan or "No METAR found.").rstrip())
        except Exception as e:
            err = f"Error: {e}"
            self.route_loadsheet_output.insert('end', err)
            self.route_route_output.insert('end', err)
            self.sid_fix_output.insert('end', err)
            self.star_fix_output.insert('end', err)
            self.route_metar_origin_output.insert('end', err)
            self.route_metar_dest_output.insert('end', err)

    def update_metar_origin(self):
        origin = self.route_origin.get().strip().upper()
        self.route_metar_origin_output.delete('1.0', 'end')
        if not origin:
            self.route_metar_origin_output.insert('end', "Please enter origin ICAO.")
            return
        try:
            self.helper.plan = ''
            self.helper.get_metar(origin)
            self.route_metar_origin_output.insert('end', (self.helper.plan or "No METAR found.").rstrip())
        except Exception as e:
            self.route_metar_origin_output.insert('end', f"Error: {e}")

    def update_metar_dest(self):
        dest = self.route_dest.get().strip().upper()
        self.route_metar_dest_output.delete('1.0', 'end')
        if not dest:
            self.route_metar_dest_output.insert('end', "Please enter destination ICAO.")
            return
        try:
            self.helper.plan = ''
            self.helper.get_metar(dest)
            self.route_metar_dest_output.insert('end', (self.helper.plan or "No METAR found.").rstrip())
        except Exception as e:
            self.route_metar_dest_output.insert('end', f"Error: {e}")

    def search_sid_fix(self):
        origin = self.route_origin.get().strip().upper()
        fix = self.sid_fix_entry.get().strip().upper()
        self.sid_fix_output.delete('1.0', 'end')
        if not origin or not fix:
            self.sid_fix_output.insert('end', "Please enter origin ICAO and fix.")
            return
        try:
            self.helper.get_file_data(f'{self.helper.data_path}/{origin}.dat')
            self.helper.plan = ''
            self.helper.search_in_dict(self.helper.structure_data(self.helper.sids), fix)
            self.sid_fix_output.insert('end', (self.helper.plan or "No SID fix found.").rstrip())
        except Exception as e:
            self.sid_fix_output.insert('end', f"Error: {e}")

    def search_star_fix(self):
        dest = self.route_dest.get().strip().upper()
        fix = self.star_fix_entry.get().strip().upper()
        self.star_fix_output.delete('1.0', 'end')
        if not dest or not fix:
            self.star_fix_output.insert('end', "Please enter destination ICAO and fix.")
            return
        try:
            self.helper.get_file_data(f'{self.helper.data_path}/{dest}.dat')
            self.helper.plan = ''
            self.helper.search_in_dict(self.helper.structure_data(self.helper.stars), fix)
            self.star_fix_output.insert('end', (self.helper.plan or "No STAR fix found.").rstrip())
        except Exception as e:
            self.star_fix_output.insert('end', f"Error: {e}")

def main():
    """Main entry point for the GUI app."""
    app = tb.Window(themename=THEME_DARK)
    RouteHelperGUI(app)
    app.mainloop()

if __name__ == "__main__":
    main()
